# Copyright 2016 Google Inc. All Rights Reserved.
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
# ==============================================================================

#!/usr/bin/env python2.7

"""A client that talks to tensorflow_model_server loaded with mnist model.

The client downloads test images of mnist data set, queries the service with
such test images to get predictions, and calculates the inference error rate.

Typical usage example:

    mnist_client.py --num_tests=100 --server=localhost:9000
"""

from __future__ import print_function

import sys
import threading
import json
import base64

# This is a placeholder for a Google-internal import.

import grpc
import numpy
import tensorflow as tf

from tensorflow_serving.apis import predict_pb2
from tensorflow_serving.apis import prediction_service_pb2_grpc
import mnist_input_data

from BaseHTTPServer import HTTPServer
from BaseHTTPServer import BaseHTTPRequestHandler


tf.app.flags.DEFINE_integer('concurrency', 1,
                            'maximum number of concurrent inference requests')
tf.app.flags.DEFINE_integer('num_tests', 100, 'Number of test images')
tf.app.flags.DEFINE_string('server', '', 'PredictionService host:port')
tf.app.flags.DEFINE_string('work_dir', '/app', 'Working directory. ')
FLAGS = tf.app.flags.FLAGS


class _ResultCounter(object):
  """Counter for the prediction results."""

  def __init__(self, num_tests, concurrency):
    self._num_tests = num_tests
    self._concurrency = concurrency
    self._error = 0
    self._done = 0
    self._active = 0
    self._condition = threading.Condition()

  def inc_error(self):
    with self._condition:
      self._error += 1

  def inc_done(self):
    with self._condition:
      self._done += 1
      self._condition.notify()

  def dec_active(self):
    with self._condition:
      self._active -= 1
      self._condition.notify()

  def get_error_rate(self):
    with self._condition:
      while self._done != self._num_tests:
        self._condition.wait()
      return self._error / float(self._num_tests)

  def throttle(self):
    with self._condition:
      while self._active == self._concurrency:
        self._condition.wait()
      self._active += 1

class RequestHandler(BaseHTTPRequestHandler):
  def do_GET(self):
    self.send_response(200)
    self.send_header('Content-type', 'plain/text')
    self.end_headers()
    self.wfile.write('Tensorflow Serving REST Proxy Server')

  def do_POST(self):
    content_len = int(self.headers.getheader('content-length', 0))
    body = self.rfile.read(content_len)
    input_data = json.loads(body)
    #print('input_data:\n%s%%' % input_data);
    #print('input_data[num_tests]:\n%s%%' % input_data['num_tests'])

    error_rate = do_inference(FLAGS.server, FLAGS.work_dir, FLAGS.concurrency, input_data['num_tests'])
    #FLAGS.concurrency, FLAGS.num_tests)
    outputs = {}
    outputs['error_rate'] = error_rate
    self.send_response(200)
    self.send_header('Content-type', 'application/json')
    self.end_headers()
    self.wfile.write(json.dumps(outputs))

def _create_rpc_callback(label, result_counter):
  """Creates RPC callback function.

  Args:
    label: The correct label for the predicted example.
    result_counter: Counter for the prediction result.
  Returns:
    The callback function.
  """
  def _callback(result_future):
    """Callback function.

    Calculates the statistics for the prediction result.

    Args:
      result_future: Result future of the RPC.
    """
    exception = result_future.exception()
    if exception:
      result_counter.inc_error()
      print(exception)
    else:
      sys.stdout.write('.')
      sys.stdout.flush()
      response = numpy.array(
          result_future.result().outputs['scores'].float_val)
      prediction = numpy.argmax(response)
      if label != prediction:
        result_counter.inc_error()
    result_counter.inc_done()
    result_counter.dec_active()
  return _callback


def do_inference(hostport, work_dir, concurrency, num_tests):
  """Tests PredictionService with concurrent requests.

  Args:
    hostport: Host:port address of the PredictionService.
    work_dir: The full path of working directory for test data set.
    concurrency: Maximum number of concurrent requests.
    num_tests: Number of test images to use.

  Returns:
    The classification error rate.

  Raises:
    IOError: An error occurred processing test data set.
  """
  test_data_set = mnist_input_data.read_data_sets(work_dir).test
  channel = grpc.insecure_channel(hostport)
  #print('hostport:\n%s%%' % hostport);
  #print('channel:\n%s%%' % channel);
  stub = prediction_service_pb2_grpc.PredictionServiceStub(channel)
  result_counter = _ResultCounter(num_tests, concurrency)
  for _ in range(num_tests):
    request = predict_pb2.PredictRequest()
    request.model_spec.name = 'mnist'
    request.model_spec.signature_name = 'predict_images'
    image, label = test_data_set.next_batch(1)
    #print('image base64 str:\n%s%%' % base64.encodestring(image[0]));
    request.inputs['images'].CopyFrom(
        tf.contrib.util.make_tensor_proto(image[0], shape=[1, image[0].size]))
    #print('request:\n%s%%' % request);
    #print('request:\n%s%%' % json.dumps(request));
    result_counter.throttle()
    #print('stub:\n%s%%' % stub);
    #print('stub.Predict:\n%s%%' % stub.Predict);
    result_future = stub.Predict.future(request, 5.0)  # 5 seconds
    #print('result_future:\n%s%%' % result_future);
    print('\n')
    print('label%s%%' % label);
    print('result_future.socres%s%%' % numpy.array(
          result_future.result().outputs['scores'].float_val))
    print('\n')
    result_future.add_done_callback(
        _create_rpc_callback(label[0], result_counter))
  return result_counter.get_error_rate()


def main(_):
  if FLAGS.num_tests > 10000:
    print('num_tests should not be greater than 10k')
    return
  if not FLAGS.server:
    print('please specify server host:port')
    return
  error_rate = do_inference(FLAGS.server, FLAGS.work_dir,
                            FLAGS.concurrency, FLAGS.num_tests)
  print('\nInference error rate: %s%%' % (error_rate * 100))


if __name__ == '__main__':
  #tf.app.run()
  server = HTTPServer(('0.0.0.0', 8888), RequestHandler)
  print('starting tensorflow-serving proxy server on 0.0.0.0:8888')
  server.serve_forever()
