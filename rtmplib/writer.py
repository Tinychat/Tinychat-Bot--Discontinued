import logging

from pyamf import amf0, amf3
import pyamf.util.pure

from . import header, rtmp_type

log = logging.getLogger(__name__)


class RtmpWriter:
    """ This class writes RTMP messages into a stream. """

    # default chunk size
    chunk_size = 128

    def __init__(self, stream):
        """ Initialize the RTMP writer and set it to write into the specified stream. """
        self.stream = stream

        self.stream_id = 0

    def flush(self):
        """ Flush the underlying stream. """
        self.stream.flush()

    def write(self, message):
        log.debug('send %r', message)
        """ Encode and write the specified message into the stream. """
        datatype = message['msg']
        body_stream = pyamf.util.BufferedByteStream()
        encoder = amf0.Encoder(body_stream)

        if datatype == rtmp_type.DT_USER_CONTROL:
            body_stream.write_ushort(message['event_type'])
            body_stream.write(message['event_data'])
            self.send_msg(datatype, body_stream.getvalue())

        elif datatype == rtmp_type.DT_WINDOW_ACK_SIZE:
            body_stream.write_ulong(message['window_ack_size'])
            self.send_msg(datatype, body_stream.getvalue())

        elif datatype == rtmp_type.DT_SET_PEER_BANDWIDTH:
            body_stream.write_ulong(message['window_ack_size'])
            body_stream.write_uchar(message['limit_type'])
            self.send_msg(datatype, body_stream.getvalue())

        elif datatype == rtmp_type.DT_COMMAND:
            for command in message['command']:
                encoder.writeElement(command)

            if 'closeStream' in message['command']:
                self.send_msg(datatype, body_stream.getvalue(), stream_id=self.stream_id)

            elif 'deleteStream' in message['command']:
                self.send_msg(datatype, body_stream.getvalue(), stream_id=self.stream_id)

            elif 'publish' in message['command']:
                self.send_msg(datatype, body_stream.getvalue(), stream_id=self.stream_id)

            elif 'play' in message['command']:
                self.send_msg(datatype, body_stream.getvalue(), chunk_id=8, stream_id=self.stream_id)

            else:
                self.send_msg(datatype, body_stream.getvalue())

        elif datatype == rtmp_type.DT_AMF3_COMMAND:
            encoder = amf3.Encoder(body_stream)
            for command in message['command']:
                encoder.writeElement(command)
            self.send_msg(datatype, body_stream.getvalue())

        elif datatype == rtmp_type.DT_SHARED_OBJECT:
            encoder.serialiseString(message['obj_name'])
            body_stream.write_ulong(message['curr_version'])
            body_stream.write(message['flags'])

            for event in message['events']:
                self.write_shared_object_event(event, body_stream)
            self.send_msg(datatype, body_stream.getvalue())
        else:
            assert False, message

    @staticmethod
    def write_shared_object_event(event, body_stream):
        inner_stream = pyamf.util.BufferedByteStream()
        encoder = amf0.Encoder(inner_stream)

        event_type = event['type']
        if event_type == rtmp_type.SO_USE:
            assert event['data'] == '', event['data']

        elif event_type == rtmp_type.SO_CHANGE:
            for attrib_name in event['data']:
                attrib_value = event['data'][attrib_name]
                encoder.serialiseString(attrib_name)
                encoder.writeElement(attrib_value)

        elif event['type'] == rtmp_type.SO_CLEAR:
            assert event['data'] == '', event['data']

        elif event['type'] == rtmp_type.SO_USE_SUCCESS:
            assert event['data'] == '', event['data']

        else:
            assert False, event

        body_stream.write_uchar(event_type)
        body_stream.write_ulong(len(inner_stream))
        body_stream.write(inner_stream.getvalue())

    def send_msg(self, data_type, body, chunk_id=3, stream_id=0, timestamp=0):
        """
        Helper method that send the specified message into the stream. Takes
        care to prepend the necessary headers and split the message into
        appropriately sized chunks.
        """
        # Values that just work. :-)
        if 1 <= data_type <= 7:
            _channel_id = 2
            _stream_id = 0
        else:
            _channel_id = chunk_id
            _stream_id = stream_id

        _header = header.Header(
            channel_id=_channel_id,  # i am pretty sure this is the chunk stream ID. Rename in header?
            stream_id=_stream_id,
            data_type=data_type,
            body_length=len(body),
            timestamp=timestamp)
        header.encode(self.stream, _header)

        for i in xrange(0, len(body), self.chunk_size):
            chunk = body[i:i + self.chunk_size]
            self.stream.write(chunk)
            if i+self.chunk_size < len(body):
                header.encode(self.stream, _header, _header)
