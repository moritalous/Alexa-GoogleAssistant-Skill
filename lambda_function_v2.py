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
import subprocess
import uuid

import boto3

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

api_endpoint = 'embeddedassistant.googleapis.com'
grpc_deadline = 60 * 3 + 5

credentials_json = os.getenv('GA_CREDENTIALS','{"token_uri": "token_uri", "client_id": "client_id", "refresh_token": "refresh_token", "scopes": ["scopes"], "client_secret": "client_secret"}')
lang = os.getenv('GA_LANG', 'en-US') # en-US, ja-JP
device_model_id = os.getenv('GA_DEVICE_MODEL_ID', 'XXXXX')
device_id = os.getenv('GA_DEVICE_ID', 'XXXXX')
error_msg=os.getenv('GA_ERROR_MSG', 'No Response')
reprompt_msg=os.getenv('GA_REPROMPT_MSG', 'Continue')
aws_region=os.getenv('AWS_S3_REGION', 'ap-northeast-1')
s3_bucket=os.getenv('AWS_S3_BUCKET', 'XXXXX')

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
                    encoding='MP3',
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

        audio_url =save_and_upload(response_audio_data)

        text_response = display_text
        if text_response == None:
            logging.info('Response text is None')
            text_response = error_msg

        session_attributes={}
        card_title=text_query
        # speech_output=text_response
        # reprompt_text=text_response
        should_end_session=False

        ssml_output="<speak><audio src='"+ audio_url +"' /></speak>"

        return build_response(session_attributes, build_speechlet_response(
        card_title, ssml_output, text_response, should_end_session))

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

def build_speechlet_response(title, output, text_response, should_end_session):
    return {
        'outputSpeech': {
            'type': 'SSML',
            'ssml': output
        },
        'card': {
            'type': 'Simple',
            'title': title,
            'content': text_response
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_msg
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

def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.

    Is not called when the skill returns should_end_session=true
    """
    print("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # add cleanup logic here


# ----------------file save and upload-----------
def save_and_upload(binary):
    tmp_file = '/tmp/temp.mp3'
    converted_file = '/tmp/temp2.mp3'
    s3_filename = str(uuid.uuid1())+'.mp3'

    if os.path.exists(tmp_file):
        os.remove(tmp_file)
    if os.path.exists(converted_file):
        os.remove(converted_file)

    save_file(tmp_file, binary)
    convert(tmp_file, converted_file)
    upload_file(converted_file, s3_bucket, s3_filename)
    url = generate_url_json(s3_bucket, s3_filename)

    return url
# ----------------file save----------------------
def save_file(output_path, binary):
    with open(output_path, "wb") as fout:          
            fout.write(binary)

# ----------------ffmpeg-------------------------
def convert(input_path, output_path):
    try:
        command = './ffmpeg -i '+input_path+' -ac 2 -codec:a libmp3lame -b:a 48k -ar 16000 -af volume=2.0 ' + output_path
        output = subprocess.check_output(
            command, stderr=subprocess.STDOUT, shell=True, timeout=3,
            universal_newlines=True)
    except subprocess.CalledProcessError as exc:
        print("Status : FAIL", exc.returncode, exc.output)
    else:
        print("Output: \n{}\n".format(output))

# ----------------Amazon S3----------------------
def upload_file(upload_path, bucket, key):
    s3_client = boto3.client('s3')
    s3_client.upload_file(upload_path, bucket, key)

def generate_url_json(bucket, key):
    return 'https://s3-'+aws_region+'.amazonaws.com/'+bucket+'/'+key

# --------------- Main handler ------------------

def lambda_handler(event, context):

    if event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])
    
    text_query=event['request']['intent']['slots']['q']['value']
    logging.info('Query text is %s', text_query)

    return assist(text_query=text_query)

if __name__ == '__main__':
    event = {
        'request':{
            'intent':{
                'slots':{
                    'q':{
                        'value':'What time is it'
                    }
                }
            },
            'type': 'IntentRequest'
        }
    }
    
    ret = lambda_handler(event, None)

    logging.info('Response \n %s', ret)
