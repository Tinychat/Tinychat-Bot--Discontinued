import logging

from pyamf import amf0, amf3
import pyamf.util.pure

from . import header, rtmp_type

log = logging.getLogger(__name__)


class RtmpReader:
    """ This class reads RTMP messages from a stream. """

    # default chunk size
    chunk_size = 128

    def __init__(self, stream):
        """
        Initialize the RTMP reader and set it to read from the specified stream.
        """
        self.stream = stream
        self.prv_header = None

    def __iter__(self):
        # AttributeError: 'NoneType' object has no attribute 'next'
        # NOTE: I am not sure when/why this happens,
        # but it hasn't occurred since i did this change
        if self is not None:
            return self

    def next(self):
        """ Read one RTMP message from the stream and return it. """
        if self.stream.at_eof():
            raise StopIteration
        # Read the message into body_stream. The message may span a number of
        # chunks (each one with its own header).
        message_body = []
        msg_body_len = 0
        _header = header.decode(self.stream)
        log.debug('header %s' % _header)

        # FIXME: this should really be implemented inside header_decode
        if _header.data_type == rtmp_type.DT_NONE:
            _header = self.prv_header
        self.prv_header = _header

        while True:
            # NOTE: this whole loop section needs to be looked at.
            read_bytes = min(_header.body_length - msg_body_len, self.chunk_size)

            message_body.append(self.stream.read(read_bytes))
            msg_body_len += read_bytes
            if msg_body_len >= _header.body_length:
                break
            next_header = header.decode(self.stream)
            # WORKAROUND: even though the RTMP specification states that the
            # extended timestamp field DOES NOT follow type 3 chunks, it seems
            # that Flash player 10.1.85.3 and Flash Media Server 3.0.2.217 send
            # and expect this field here.
            if _header.timestamp >= 0x00ffffff:
                self.stream.read_ulong()
            assert next_header.stream_id == -1, (_header, next_header)
            assert next_header.data_type == -1, (_header, next_header)
            assert next_header.timestamp == -1, (_header, next_header)
            assert next_header.body_length == -1, (_header, next_header)
        assert _header.body_length == msg_body_len, (_header, msg_body_len)
        body_stream = pyamf.util.BufferedByteStream(''.join(message_body))

        # Decode the message based on the datatype present in the header
        ret = {'msg': _header.data_type}

        if ret['msg'] == rtmp_type.DT_NONE:
            log.warning('WARNING: message with datatype None received: %s' % _header)
            return self.next()

        elif ret['msg'] == rtmp_type.DT_USER_CONTROL:
            ret['event_type'] = body_stream.read_ushort()
            ret['event_data'] = body_stream.read()

        elif ret['msg'] == rtmp_type.DT_WINDOW_ACK_SIZE:
            ret['window_ack_size'] = body_stream.read_ulong()

        elif ret['msg'] == rtmp_type.DT_SET_PEER_BANDWIDTH:
            ret['window_ack_size'] = body_stream.read_ulong()
            ret['limit_type'] = body_stream.read_uchar()

        elif ret['msg'] == rtmp_type.DT_SHARED_OBJECT:
            decoder = amf0.Decoder(body_stream)
            obj_name = decoder.readString()
            curr_version = body_stream.read_ulong()
            flags = body_stream.read(8)
            # A shared object message may contain a number of events.
            events = []
            while not body_stream.at_eof():
                event = self.read_shared_object_event(body_stream, decoder)
                events.append(event)

            ret['obj_name'] = obj_name
            ret['curr_version'] = curr_version
            ret['flags'] = flags
            ret['events'] = events

        elif ret['msg'] == rtmp_type.DT_AMF3_SHARED_OBJECT:
            decoder = amf3.Decoder(body_stream)
            obj_name = decoder.readString()
            curr_version = body_stream.read_ulong()
            flags = body_stream.read(8)
            # A shared object message may contain a number of events.
            events = []
            while not body_stream.at_eof():
                event = self.read_shared_object_event(body_stream, decoder)
                events.append(event)

            ret['obj_name'] = obj_name
            ret['curr_version'] = curr_version
            ret['flags'] = flags
            ret['events'] = events

        elif ret['msg'] == rtmp_type.DT_COMMAND:
            decoder = amf0.Decoder(body_stream)
            commands = []
            while not body_stream.at_eof():
                commands.append(decoder.readElement())
            ret['command'] = commands

        elif ret['msg'] == rtmp_type.DT_AMF3_COMMAND:
            decoder = amf3.Decoder(body_stream)
            commands = []
            while not body_stream.at_eof():
                commands.append(decoder.readElement())
            ret['command'] = commands

        elif ret['msg'] == rtmp_type.DT_SET_CHUNK_SIZE:
            ret['chunk_size'] = body_stream.read_ulong()
        else:
            assert False, _header

        log.debug('recv %r', ret)
        return ret

    @staticmethod
    def read_shared_object_event(body_stream, decoder):
        """
        Helper method that reads one shared object event found inside a shared
        object RTMP message.
        """
        so_body_type = body_stream.read_uchar()
        so_body_size = body_stream.read_ulong()

        event = {'type': so_body_type}
        if event['type'] == rtmp_type.SO_USE:
            assert so_body_size == 0, so_body_size
            event['data'] = ''

        elif event['type'] == rtmp_type.SO_RELEASE:
            assert so_body_size == 0, so_body_size
            event['data'] = ''

        elif event['type'] == rtmp_type.SO_CHANGE:
            start_pos = body_stream.tell()
            changes = {}
            while body_stream.tell() < start_pos + so_body_size:
                attrib_name = decoder.readString()
                attrib_value = decoder.readElement()
                assert attrib_name not in changes, (attrib_name, changes.keys())
                changes[attrib_name] = attrib_value
            assert body_stream.tell() == start_pos + so_body_size,\
                (body_stream.tell(), start_pos, so_body_size)
            event['data'] = changes

        elif event['type'] == rtmp_type.SO_SEND_MESSAGE:
            start_pos = body_stream.tell()
            msg_params = []
            while body_stream.tell() < start_pos + so_body_size:
                msg_params.append(decoder.readElement())
            assert body_stream.tell() == start_pos + so_body_size,\
                (body_stream.tell(), start_pos, so_body_size)
            event['data'] = msg_params

        elif event['type'] == rtmp_type.SO_CLEAR:
            assert so_body_size == 0, so_body_size
            event['data'] = ''

        elif event['type'] == rtmp_type.SO_REMOVE:
            event['data'] = decoder.readString()

        elif event['type'] == rtmp_type.SO_USE_SUCCESS:
            assert so_body_size == 0, so_body_size
            event['data'] = ''

        else:
            assert False, event['type']

        return event
