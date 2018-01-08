# Copyright (C) 2017 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import os
import logging
import json

import google.auth.transport.grpc
import google.auth.transport.requests
import google.oauth2.credentials

from google.assistant.embedded.v1alpha2 import (
    embedded_assistant_pb2,
    embedded_assistant_pb2_grpc
)

from googlesamples.assistant.grpc import (
    assistant_helpers
)

import wave

api_endpoint = 'embeddedassistant.googleapis.com'
grpc_deadline = 60 * 3 + 5

credentials_json = os.getenv('GA_CREDENTIALS','{"token_uri": "token_uri", "client_id": "client_id", "refresh_token": "refresh_token", "scopes": ["scopes"], "client_secret": "client_secret"}')
lang = os.getenv('GA_LANG', 'en-US') # en-US, ja-JP
device_model_id = os.getenv('GA_DEVICE_MODEL_ID', 'XXXXX')
device_id = os.getenv('GA_DEVICE_ID', 'XXXXX')
error_msg=os.getenv('GA_ERROR_MSG', 'No Response')

# Setup logging.
logging.basicConfig(level=logging.INFO)

# ---------------
class SampleTextAssistant(object):
    """Sample Assistant that supports text based conversations.
    Args:
      language_code: language for the conversation.
      device_model_id: identifier of the device model.
      device_id: identifier of the registered device instance.
      channel: authorized gRPC channel for connection to the
        Google Assistant API.
      deadline_sec: gRPC deadline in seconds for Google Assistant API call.
    """

    def __init__(self, language_code, device_model_id, device_id,
                 channel, deadline_sec):
        self.language_code = language_code
        self.device_model_id = device_model_id
        self.device_id = device_id
        self.conversation_state = None
        self.assistant = embedded_assistant_pb2_grpc.EmbeddedAssistantStub(
            channel
        )
        self.deadline = deadline_sec

    def __enter__(self):
        return self

    def __exit__(self, etype, e, traceback):
        if e:
            return False

    def assist(self, text_query):
        """Send a text request to the Assistant and playback the response.
        """
        def iter_assist_requests():
            dialog_state_in = embedded_assistant_pb2.DialogStateIn(
                language_code=self.language_code,
                conversation_state=b''
            )
            if self.conversation_state:
                dialog_state_in.conversation_state = self.conversation_state
            config = embedded_assistant_pb2.AssistConfig(
                audio_out_config=embedded_assistant_pb2.AudioOutConfig(
                    encoding='LINEAR16',
                    sample_rate_hertz=16000,
                    volume_percentage=100,
                ),
                dialog_state_in=dialog_state_in,
                device_config=embedded_assistant_pb2.DeviceConfig(
                    device_id=self.device_id,
                    device_model_id=self.device_model_id,
                ),
                text_query=text_query,
            )
            req = embedded_assistant_pb2.AssistRequest(config=config)
            assistant_helpers.log_assist_request_without_audio(req)
            yield req

        display_text = None
        response_audio_data = b''
        for resp in self.assistant.Assist(iter_assist_requests(),
                                          self.deadline):
            assistant_helpers.log_assist_response_without_audio(resp)

            if resp.dialog_state_out.conversation_state:
                conversation_state = resp.dialog_state_out.conversation_state
                self.conversation_state = conversation_state
            if resp.audio_out.audio_data:
                response_audio_data += resp.audio_out.audio_data
                
            if resp.dialog_state_out.supplemental_display_text:
                display_text = resp.dialog_state_out.supplemental_display_text
        
        w = wave.Wave_write("output.wav")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(response_audio_data)
        w.close()

        return display_text 
# ---------------

def assist(text_query):
    credentials = google.oauth2.credentials.Credentials(token=None,
                                                        **json.loads(credentials_json))
    http_request = google.auth.transport.requests.Request()
    credentials.refresh(http_request)

    # Create an authorized gRPC channel.
    grpc_channel = google.auth.transport.grpc.secure_authorized_channel(
        credentials, http_request, api_endpoint)

    with SampleTextAssistant(lang, device_model_id, device_id,
                                grpc_channel, grpc_deadline) as assistant:
        text_response = assistant.assist(text_query=text_query)
        return text_response

# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': title,
            'content': output
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }

def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }

# --------------- Main handler ------------------

def lambda_handler(event, context):
    text_query=text_query=event['request']['intent']['slots']['q']['value']
    logging.info('Query text is %s', text_query)

    text_response = assist(text_query=text_query)
    if text_response == None:
        logging.info('Response text is None')
        text_response = error_msg

    logging.info('Response text is %s', text_response)

    session_attributes={}
    card_title=text_query+' -> ' + text_response
    speech_output=text_response
    reprompt_text=text_response
    should_end_session=True
    
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))

if __name__ == '__main__':
    event = {
        'request':{
            'intent':{
                'slots':{
                    'q':{
                        'value':'What time is it'
                    }
                }
            }
        }
    }
    
    lambda_handler(event, None)
