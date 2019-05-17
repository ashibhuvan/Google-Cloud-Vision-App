# Copyright 2017 Google Inc. All Rights Reserved.
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

from datetime import datetime
import logging
import os
import base64
from flask import Flask, redirect, render_template, request
from io import BytesIO
from google.cloud import datastore
from google.cloud import storage
import random
from google.cloud import vision
import string


CLOUD_STORAGE_BUCKET = os.environ.get('CLOUD_STORAGE_BUCKET')


app = Flask(__name__)


@app.route('/')
def homepage():
    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Use the Cloud Datastore client to fetch information from Datastore about
    # each photo.
    query = datastore_client.query(kind='Faces')
    image_entities = list(query.fetch())

    # Return a Jinja2 HTML template and pass in image_entities as a parameter.
    return render_template('homepage.html', image_entities=image_entities)


@app.route('/upload_photo', methods=['GET', 'POST'])
def upload_photo():
 
    photo = request.files['file']
    
    random1 = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(5)])
    new_path = random1 + photo.filename
    # Create a Cloud Storage client.
    storage_client = storage.Client()

    # Get the bucket that the file will be uploaded to.
    bucket = storage_client.get_bucket(CLOUD_STORAGE_BUCKET)

    # Create a new blob and upload the file's content.
    blob = bucket.blob(new_path)
    blob.upload_from_string(
            photo.read(), content_type=photo.content_type)

    # Make the blob publicly viewable.
    blob.make_public()


    # Create a Cloud Vision client.
    vision_client = vision.ImageAnnotatorClient()

    # Use the Cloud Vision client to detect a face for our image.
    source_uri = 'gs://{}/{}'.format(CLOUD_STORAGE_BUCKET, blob.name)
    image = vision.types.Image(
        source=vision.types.ImageSource(gcs_image_uri=source_uri))
    faces = vision_client.face_detection(image).face_annotations

    response = vision_client.label_detection(image=image)
    labels = response.label_annotations
    label = ""
  
    if labels:
        if len(labels) < 5:
            for j in labels:
                label = label + ", " + j.description
        else:
            for i in range(5):
                label = label + ", " + labels[i].description
        label = label[1:]
    else:
        label = "No labels found" 




    response = vision_client.logo_detection(image=image)
    logos = response.logo_annotations
    logo = ""
    if len(logos) > 0:
        for i in logos:
    
            logo = logo + ", " + i.description
        logo = logo[1:]
    else:
        logo = "No Logos Found"

    
    response = vision_client.web_detection(image=image)
    annotations = response.web_detection

    label_web_guess = ""
    
    length_of = len(annotations.web_entities)
    if annotations.web_entities:
        if len(annotations.web_entities) < 5:
            for j in annotations.web_entities:
                label_web_guess = label_web_guess + ", " + j.description
        else:
            for i in range(5):
                label_web_guess = label_web_guess + ", " + annotations.web_entities[i].description
        label_web_guess = label_web_guess[1:]
    else:
        label_web_guess = "No web results found" 


    url_similar_image = ""
    if annotations.visually_similar_images:
        url_similar_image = annotations.visually_similar_images[0].url

    else:
        url_similar_image = ""

    
    # If a face is detected, save to Datastore the likelihood that the face
    # displays 'joy,' as determined by Google's Machine Learning algorithm.
    if len(faces) > 0:
        face = faces[0]

        # Convert the likelihood string.
        likelihoods = [
            'Unknown', 'Very Unlikely', 'Unlikely', 'Possible', 'Likely',
            'Very Likely']
        face_joy = likelihoods[face.joy_likelihood]
    else:
        face_joy = 'Unknown'



    response = vision_client.text_detection(image=image)
    texts = response.text_annotations
    text_lifted = ""
    if texts:

        for text in texts:
            print('\n"{}"'.format(text.description))
            text_lifted = text_lifted + " " + text.description
    else:
        text_lifted = "No Text Found"



    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Fetch the current date / time.
    current_datetime = datetime.now()

    # The kind for the new entity.
    kind = 'Faces'

    # The name/ID for the new entity.
    name = blob.name

    # Create the Cloud Datastore key for the new entity.
    key = datastore_client.key(kind, name)

    # Construct the new entity using the key. Set dictionary values for entity
    # keys blob_name, storage_public_url, timestamp, and joy.
    entity = datastore.Entity(key)
    entity['blob_name'] = blob.name
    entity['image_public_url'] = blob.public_url
    entity['timestamp'] = current_datetime
    entity['joy'] = face_joy
    entity['label'] = label
    entity['logos_detected'] = logo
    entity['best_guess'] = label_web_guess
    entity['number_found'] = length_of
    entity['text'] = text_lifted
    entity['image_url'] = url_similar_image


    # Save the new entity to Datastore.
    datastore_client.put(entity)

    # Redirect to the home page.

    return redirect('/')


@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500


if __name__ == '__main__':
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host='127.0.0.1', port=8080, debug=True)
