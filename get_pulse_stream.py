from lib.device import Stream
from lib.processors import findFaceGetPulse
from lib.interface import plotXY, imshow, waitKey,destroyWindow, moveWindow, resize
import numpy as np
import sys, time, urllib, urllib2, re
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

class getPulseApp(object):
    """
    Python application that finds a face in a webcam stream, then isolates the
    forehead.

    Then the average green-light intensity in the forehead region is gathered
    over time, and the detected person's pulse is estimated.
    """
    def __init__(self, dir):
        #Imaging device - must be a connected stream (not an ip camera or mjpeg
        #stream)

        self.stream = Stream(dir)
        self.workout_slot_id = self.get_slot_id(dir)
        self.w,self.h = 0,0

        #Containerized analysis of recieved image frames (an openMDAO assembly)
        #is defined next.

        #This assembly is designed to handle all image & signal analysis,
        #such as face detection, forehead isolation, time series collection,
        #heart-beat detection, etc.

        #Basically, everything that isn't communication
        #to the camera device or part of the GUI
        self.processor = findFaceGetPulse(bpm_limits = [50,160],
                                          data_spike_limit = 25.,
                                          face_detector_smoothness = 10.)

        #Init parameters for the cardiac data plot
        self.bpm_plot = False
        self.plot_title = "Cardiac info - raw signal, filtered signal, and PSD"

        #Maps keystrokes to specified methods
        #(A GUI window must have focus for these to work)
        self.key_controls = {"s" : self.toggle_search,
                        "d" : self.toggle_display_plot}
        self.bpm = 0

    def get_slot_id(self, dir):
      pattern = "(\d+)"
      matcher = re.compile(pattern)
      match   = matcher.search(dir)

      if match <> None:
        return match.group()
      return 1

    def toggle_search(self):
        """
        Toggles a motion lock on the processor's face detection component.

        Locking the forehead location in place significantly improves
        data quality, once a forehead has been sucessfully isolated.
        """
        state = self.processor.find_faces.toggle()
        print "face detection lock =",not state

    def toggle_display_plot(self):
        """
        Toggles the data display.
        """
        if self.bpm_plot:
            print "bpm plot disabled"
            self.bpm_plot = False
            destroyWindow(self.plot_title)
        else:
            print "bpm plot enabled"
            self.bpm_plot = True
            self.make_bpm_plot()
            moveWindow(self.plot_title, self.w,0)

    def make_bpm_plot(self):
        """
        Creates and/or updates the data display
        """
        plotXY([[self.processor.fft.times,
                 self.processor.fft.samples],
            [self.processor.fft.even_times[4:-4],
             self.processor.measure_heart.filtered[4:-4]],
                [self.processor.measure_heart.freqs,
                 self.processor.measure_heart.fft]],
               labels = [False, False, True],
               showmax = [False,False, "bpm"],
               label_ndigits = [0,0,0],
               showmax_digits = [0,0,1],
               skip = [3,3,4],
               name = self.plot_title,
               bg = self.processor.grab_faces.slices[0])

    def key_handler(self):
        """
        Handle keystrokes, as set at the bottom of __init__()

        A plotting or camera frame window must have focus for keypresses to be
        detected.
        """
        pressed = waitKey(10) & 255 #wait for keypress for 10 ms
        if pressed == 27: #exit program on 'esc'
            quit()
        for key in self.key_controls.keys():
            if chr(pressed) == key:
                self.key_controls[key]()

    def print_data(self):
        print "BPM: {0}".format(self.processor.fft.samples)

    def main_loop(self):
        """
        Single iteration of the application's main loop.
        """
        # Get current image frame from the camera
        (frame, frame_time) = self.stream.get_frame()
        if frame is None:
            return False
        self.h,self.w,_c = frame.shape

        #display unaltered frame
        #imshow("Original",frame)

        #set current image frame to the processor's input
        self.processor.frame_in = frame
        self.processor.time_in = frame_time
        #process the image frame to perform all needed analysis
        self.processor.run()
        #collect the output frame for display
        output_frame = self.processor.frame_out

        #show the processed/annotated output frame

        # output_frame = resize(output_frame, (640,480))
        # imshow("Processed",output_frame)

        #create and/or update the raw data display if needed
        # if self.bpm_plot:
        #     self.make_bpm_plot()
        self.bpm = self.processor.fft.samples[-1]
        print str(self.processor.time_in) + '\t' + str(self.bpm)

        return True

class MyHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        if self.path == '/crossdomain.xml':
            self.send_header('Content-type', 'text/xml')
            self.end_headers()
            self.wfile.write('<cross-domain-policy><site-control permitted-cross-domain-policies="master-only"/><allow-access-from domain="*"/><allow-http-request-headers-from domain="*" headers="*"/></cross-domain-policy>')
        else:
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            while App.main_loop():
                url = "http://localhost:3000/train/pulse_data"
                values = dict(bpm=App.bpm, captured_at=App.processor.time_in, workout_slot_id=App.workout_slot_id)
                data = urllib.urlencode(values)
                req = urllib2.Request(url, data)
                rsp = urllib2.urlopen(req)
                content = rsp.read()
                time.sleep(0.01)
            if self.path == '/':
                self.wfile.write(str(App.bpm))

            else:
                self.wfile.write(self.path[1:] + "({bpm: " + str(App.bpm) + "})")
        return
    def do_POST(self):
        self.send_response(200)
        # dump image into processing directory?
        return

if __name__ == "__main__":
    # example (replace these values)
    if len(sys.argv) < 2:
        raise Exception("Specify a directory for the webcam stream")
    App = getPulseApp(sys.argv[1])

    try:
        server = HTTPServer(('', 3001), MyHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        App.print_data()
        server.socket.close()
