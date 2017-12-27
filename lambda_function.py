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
    textinput,
    assistant_helpers
)

api_endpoint = 'embeddedassistant.googleapis.com'
grpc_deadline = 60 * 3 + 5

credentials_file = os.getenv('GA_CREDENTIALS', 'credentials.json')
lang = os.getenv('GA_LANG', 'ja-JP')
device_model_id = os.getenv('GA_DEVICE_MODEL_ID', 'XXXXX')
device_id = os.getenv('GA_DEVICE_ID', 'XXXXX')

# Setup logging.
logging.basicConfig(level=logging.INFO)

# --------------- 

def assist(text_query):

    # Load OAuth 2.0 credentials.
    with open(credentials_file, 'r') as f:
        credentials = google.oauth2.credentials.Credentials(token=None,
                                                            **json.load(f))
        http_request = google.auth.transport.requests.Request()
        credentials.refresh(http_request)

    # Create an authorized gRPC channel.
    grpc_channel = google.auth.transport.grpc.secure_authorized_channel(
        credentials, http_request, api_endpoint)

    with textinput.SampleTextAssistant(lang, device_model_id, device_id,
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
            'title': "SessionSpeechlet - " + title,
            'content': "SessionSpeechlet - " + output
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
        text_response = '応答がありませんでした'

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
                        'value':'明日の天気は'
                    }
                }
            }
        }
    }
    
    lambda_handler(event, None)
