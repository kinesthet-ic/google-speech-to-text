#!/usr/bin/env python
# coding: UTF-8

import sys
import tkinter
import threading
import pyaudio
import time
from six.moves import queue
from environs import Env

from google.api_core import exceptions

from google.cloud import speech_v1p1beta1 as speech
from google.cloud.speech_v1p1beta1 import enums
from google.cloud.speech_v1p1beta1 import types

import os


env = Env()
env.read_env()


os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = env(
    "GOOGLE_APPLICATION_CREDENTIALS")


class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""

    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk

        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1, rate=self._rate,
            input=True, frames_per_buffer=self._chunk,
            stream_callback=self._fill_buffer,
        )

        self.closed = False

        return self

    def __exit__(self, _type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True

        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, _frame_count, _time_info, _status_flags):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        """Generator."""
        while not self.closed:
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break
            yield b''.join(data)
# [END audio_stream]


class GoogleCloudSpeech:

    def __init__(self, callbacks=None, console=True, rate=16000):
        """Init."""
        if isinstance(callbacks, dict):
            for name in callbacks:
                if not callable(callbacks[name]):
                    raise ValueError("Callback {} is not callable."
                                     .format(name))
            self.callbacks = callbacks
        else:
            self.callbacks = {}

        self.rate = rate

        self.console = console

    def __print(self, text):
        if self.console:
            sys.stdout.write(text)
            sys.stdout.flush()

    def listen_print_loop(self, responses):
        num_chars_printed = 0

        for response in responses:

            if not response.results:
                continue
            result = response.results[0]
            if not result.alternatives:
                continue
            transcript = result.alternatives[0].transcript

            overwrite_chars = " " * (num_chars_printed - len(transcript))

            if not result.is_final:
                num_chars_printed = len(transcript)
                self.callbacks.get("middle", lambda x: True)(transcript)
            else:
                self.callbacks.get("transcript", lambda x: True)(transcript)
                num_chars_printed = 0
                break

    def listen(self, language_code='ja-JP'):
        """Listen."""

        client = speech.SpeechClient()
        config = types.RecognitionConfig(
            encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.rate,
            model=None,
            speech_contexts=[types.SpeechContext(
            )],
            language_code=language_code)
        streaming_config = types.StreamingRecognitionConfig(
            config=config,
            single_utterance=True,
            interim_results=True
        )

        self.callbacks.get("ready", lambda: True)()

        with MicrophoneStream(self.rate, int(self.rate/10)) as stream:

            self.callbacks.get("start", lambda: True)()

            while True:
                try:
                    audio_generator = stream.generator()
                    requests = (types.StreamingRecognizeRequest(audio_content=content)
                                for content in audio_generator)
                    responses = client.streaming_recognize(
                        streaming_config, requests)
                    self.listen_print_loop(responses)

                except exceptions.OutOfRange:
                    print("Time exceeded.(OutOfRange)")
                except exceptions.ServiceUnavailable:
                    print("Connection closed.(ServiceUnavailable)")
                except KeyboardInterrupt:
                    print("KeyboardInterrupt.")
                    break
                except:
                    print("Unexpected error:", sys.exc_info()[0])
                    raise

            self.callbacks.get("end", lambda: True)()

    def on(self, name, callfunc):
        """On."""
        if callable(callfunc):
            self.callbacks[name] = callfunc
            return True
        return False

    def off(self, name):
        """Off."""
        if name in self.callbacks:
            self.callbacks.pop(name)
            return True
        return False


def wait():
    if sys.version_info[0] == 2:
        raw_input("PRESS ENTER AND TALK\n")
    else:
        input("PRESS ENTER AND TALK\n")


def create_window(width=800, height=50):
    root = tkinter.Tk()
    root.title("Transcript ")
    root.wait_visibility(root)
    root.wm_attributes('-alpha', 0.8)
    root.geometry("{}x{}".format(width, height))

    frame = tkinter.Frame(root, width=width, height=height)

    val_text1 = tkinter.StringVar()
    text1 = tkinter.Label(text="Init.", font=("", 17), textvariable=val_text1)
    text1.pack(fill="both", side="left")

    frame.pack()

    return root, val_text1


def change_text(text):
    # TEXT.set("{}".format(text))
    print("<text>" + text + "</text>")


def talking_change_text(text):
    print("<talking>" + text + "</talking>")


if __name__ == '__main__':

    # speechモジュールの設定
    SPEECH = GoogleCloudSpeech()
    # 録音開始する前に実行されるイベント
    SPEECH.on("ready", wait)
    # 聞き取りが開始されたときに実行されるイベント
    SPEECH.on("start",
              lambda: print("<start>"))
    # 聞き取り中の結果を受信したときに実行されるイベント
    SPEECH.on("middle", talking_change_text)
    # 一文の聞き取りが確定したときに実行されるイベント
    SPEECH.on("transcript", change_text)
    # 何らかの原因で聞き取りが終了したときに実行されるイベント
    SPEECH.on("end",
              lambda: print("終了："))
    SPEECH.listen()
    # # guiの準備
    while True:
        time.sleep(0.1)
