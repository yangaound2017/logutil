# coding=utf-8

import logging, os, threading, time
from logging.handlers import MemoryHandler

from .trace import handle_exception, Trace, Traceable, LogException


__version__ = '1.0.0'


LoggerClass = logging.getLoggerClass()
logRecordFmt = "[%(levelname)s][%(asctime)s] at %(module)s.py:%(lineno)s - %(message)s"
#logRecordFmt = "[%(levelname)s][%(asctime)s] - %(message)s"


def make_handler(filename, capacity=1, format=logRecordFmt, **verbose):
    """
    Factory function that return either a new instance of `logging.Handler` or `_MemoryHandler`(with buffer).

    :param filename:
        It will be passed to create a `logging.FileHandler` if argument capacity <= 1.
    :type filename:
        `basestring`

    :param capacity:
        It will be passed to create a `_MemoryHandler` if its value greater then 1.
        Default value: 1
    :type capacity:
       `int`

    :param format:
        Format string for the instance of `logging.FileHandler`.
        Default: "[%(levelname)s][%(asctime)s] at %(module)s.py:%(lineno)s: %(message)s"
    :type format:
       `str`
    """

    filename = os.path.abspath(filename)
    if capacity > 1:
        handler = _MemoryHandler(filename, capacity, **verbose)
    else:
        if not os.path.exists(os.path.dirname(filename) or './'):
            os.makedirs(os.path.dirname(filename))
        handler = logging.FileHandler(filename)
        handler.setFormatter(logging.Formatter(format))
    return handler


class SimpleLogger(LoggerClass):
    """
    This class inherits `logging.Logger` or it's sub class, a `logging.FileHandler` will be created when it is instantiated.

    :param filename:
        Required argument; it will be used to create a `logging.FileHandler`
    :type filename:
        `basestring`

    :param level:
        Optional keyword argument; Logger level.
        Default value: 'INFO'.
    :type level:
        `str` = {"DEBUG"|"INFO"|"WARNING"|"CRITICAL"|"ERROR"}

    :param format:
        Optional keyword argument; Format string for instance of `logging.FileHandler` .
        Default value: "[%(levelname)s][%(asctime)s] at %(module)s.py:%(lineno)s - %(message)s"
    :type format:
       `str`

    :param name:
        Optional keyword argument. The name of logger; the namespace will be used if omitted.
    :type format:
        `str`

    E.g., Create and use SimpleLogger:
    >>> logger = SimpleLogger('error.log')
    >>> logger.info('msg')

    E.g., specify  optional arguments:
    >>> logger = SimpleLogger('error.log', level='INFO', format="[%(levelname)s] %(message)s", name=__name__)
    >>> logger.info('msg')
    """

    def __init__(self, filename, level='info', format=logRecordFmt, name=__name__, **verbose):
        LoggerClass.__init__(self, name)
        self.setLevel(getattr(logging, level.upper()))           # set level
        self.addHandler(make_handler(filename, format=format))   # add a handler


class TimedRotatingLogger(SimpleLogger):
    """
    This class inherits `SimpleLogger` and extends a method named `rotate_handler()` to auto rotate log file in time
    according to the argument suffixFmt. A `TimedRotatingLogger` just maintains one handler, 
    others will be popped out when `rotate_handler()` be called.

    :param filename:
        Required base filename.
    :type filename:
        `basestring`

    :param suffixFmt:
        Optional keyword argument. It will be used to call time.strftime(suffixFmt) to get the suffix of full filename,
        full_filename = filename + '.' + time.strftime(suffixFmt).
        Default: "%Y-%m-%d", it means that the log file will be rotated every day at midnight.
    :type suffixFmt:
        `str`

    E.g., Create and use TimedRotatingLogger:
    >>> logger = TimedRotatingLogger('error_log')
    >>> logger.info('msg')

    E.g., specify arguments:
    >>> logger = TimedRotatingLogger('error_log', suffixFmt='%Y-%m-%d', level='INFO', )
    >>> logger.info('msg')
    """

    def __init__(self, filename, suffixFmt='%Y-%m-%d', **handlerParams):
        super(TimedRotatingLogger, self).__init__(filename + '.' + time.strftime(suffixFmt), **handlerParams)
        self.__baseFilename = filename
        self.__suffixFmt = suffixFmt
        self.__suffix = time.strftime(self.__suffixFmt)
        self.__handlerParams = handlerParams
        self._rLock = threading.RLock()
        self.handlers = list()
        self.rotate_handler()

    def handle(self, record):
        if self.__suffix != time.strftime(self.__suffixFmt):
            with self._rLock:
                if self.__suffix != time.strftime(self.__suffixFmt):
                    self.__suffix = time.strftime(self.__suffixFmt)
                    self.rotate_handler()
        LoggerClass.handle(self, record)

    def rotate_handler(self):
        with self._rLock:
            for h in self.handlers:
                h.close()
            self.handlers = list()
            handler = make_handler(self.__baseFilename + '.' + self.__suffix, **self.__handlerParams)
            self.addHandler(handler)


class TimedRotatingMemoryLogger(TimedRotatingLogger):
    """
    This class inherits `TimedRotatingLogger` and extends a method named flush to flush buffering,
    auto flushing buffering has implemented by `_MemoryHandler`.

    :param file:
        Required base filename.
    :type file:
        `basestr`

    :param capacity:
        keyword argument, default: 100. Buffer size; if the buffering is full, the `_MemoryHandler` auto flush it.
    :type capacity:
        `int`

    :param flushInterval:
        keyword argument, default: 120 second. Flush buffering if time.time() - theLastFlushTime > flushInterval.
    :type flushInterval:
        `int`

    :param flushLevel:
        keyword argument, default: 'ERROR'. Flush buffering if the level of a logRecord greater then or equal
        the argument flushLevel.
    :type flushLevel:
        `str` = {"DEBUG"|"INFO"|"WARNING"|"CRITICAL"|"ERROR"}
    """

    def __init__(self, filename, capacity=100, flushInterval=120, flushLevel='ERROR', **kwargs):
        super(TimedRotatingMemoryLogger, self).__init__(filename, capacity=capacity, flushInterval=flushInterval,
                                                        flushLevel=getattr(logging, flushLevel.upper()), **kwargs)

    def flush(self):
        with self._rLock:
            for h in self.handlers:
                h.flush()


class _MemoryHandler(MemoryHandler):
    def __init__(self, filename, capacity, flushLevel, flushInterval, target=None, **kwargs):
        MemoryHandler.__init__(self, capacity, flushLevel, target or make_handler(filename, capacity=1, **kwargs))
        self.__flushInterval = flushInterval
        self.__lastFlushTime = time.time()
        self.__condition = threading.Condition()
        self.__flusher = None

    def shouldFlush(self, record):
        return MemoryHandler.shouldFlush(self, record) or (time.time() - self.__lastFlushTime > self.__flushInterval)\
               or (record.levelno >= self.flushLevel)

    def flush(self):
        with self.__condition:
            try:
                target, buffered, self.buffer = self.target, self.buffer, []
                self.__flusher = threading.Thread(target=self.__flush, args=(target, buffered,), name='flusher')
                self.__flusher.isDaemon() and self.__flusher.setDaemon(False)
                self.__flusher.start()
                self.__condition.wait(1.0)
            except Exception:
                self.buffer = buffered

    def __flush(self, target, buffered):
        with self.__condition:
            self.__condition.notifyAll()
        try:
            for record in buffered:
                target.handle(record)
            self.__lastFlushTime = time.time()
        except Exception:
            pass

    def close(self):
        self.flush()
        if self.__flusher and self.__flusher.is_alive():
            self.__flusher.join()
        MemoryHandler.close(self)
