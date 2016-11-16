import numpy as np
from pyrpl.attributes import FloatAttribute, BoolRegister, FloatRegister
from pyrpl.widgets.module_widgets import PidWidget

from . import FilterModule


class IValAttribute(FloatAttribute):
    """
    Attribute for integrator value
    """

    def get_value(self, instance, owner):
        return float(instance._to_pyint(instance._read(0x100), bitlength=16)) / 2 ** 13
        # bitlength used to be 32 until 16/7/2016

    def set_value(self, instance, value):
        """set the value of the register holding the integrator's sum [volts]"""
        return instance._write(0x100, instance._from_pyint(int(round(value * 2 ** 13)), bitlength=16))

class Pid(FilterModule):
    widget_class = PidWidget
    gui_attributes = ["input",
                      "output_direct",
                      "setpoint",
                      "p",
                      "i",
                      "d",
                      "ival",
                      "inputfilter"]

    setup_attributes = gui_attributes

    _delay = 3  # min delay in cycles from input to output_signal of the module
    # with integrator and derivative gain, delay is rather 4 cycles

    _PSR = 12  # Register(0x200)

    _ISR = 32  # Register(0x204)

    _DSR = 10  # Register(0x208)

    _GAINBITS = 24  # Register(0x20C)

    parameter_names = ["p",
                       "i",
                       "d",
                       "setpoint",
                       "min_voltage",
                       "max_voltage",
                       "normalization_on",
                       "normalization_i",
                       "output_direct",
                       "input",
                       "ival"]

    ival = IValAttribute(min=-4, max=4, increment= 8. / 2**16)

    setpoint = FloatRegister(0x104, bits=14, norm= 2 **13,
                             doc="pid setpoint [volts]")

    min_voltage = FloatRegister(0x124, bits=14, norm= 2 **13,
                                doc="minimum output signal [volts]")
    max_voltage = FloatRegister(0x128, bits=14, norm= 2 **13,
                                doc="maximum output signal [volts]")

    p = FloatRegister(0x108, bits=_GAINBITS, norm= 2 **_PSR,
                      doc="pid proportional gain [1]")
    i = FloatRegister(0x10C, bits=_GAINBITS, norm= 2 **_ISR * 2.0 * np.pi * 8e-9,
                      doc="pid integral unity-gain frequency [Hz]")
    d = FloatRegister(0x110, bits=_GAINBITS, norm= 2 ** _DSR /( 2.0 *np. pi *8e-9),
                      invert=True,
                      doc="pid derivative unity-gain frequency [Hz]. Off when 0.")

    @property
    def proportional(self):
        return self.p

    @property
    def integral(self):
        return self.i

    @property
    def derivative(self):
        return self.d

    @property
    def reg_integral(self):
        return self.ival

    @proportional.setter
    def proportional(self, v):
        self.p = v

    @integral.setter
    def integral(self, v):
        self.i = v

    @derivative.setter
    def derivative(self, v):
        self.d = v

    @reg_integral.setter
    def reg_integral(self, v):
        self.ival = v

    def transfer_function(self, frequencies, extradelay=0):
        """
        Returns a complex np.array containing the transfer function of the
        current PID module setting for the given frequency array. The
        settings for p, i, d and inputfilter, as well as delay are aken into
        account for the modelisation. There is a slight dependency of delay
        on the setting of inputfilter, i.e. about 2 extracycles per filter
        that is not set to 0, which is however taken into account.

        Parameters
        ----------
        frequencies: np.array or float
            Frequencies to compute the transfer function for
        extradelay: float
            External delay to add to the transfer function (in s). If zero,
            only the delay for internal propagation from input to
            output_signal is used. If the module is fed to analog inputs and
            outputs, an extra delay of the order of 200 ns must be passed as
            an argument for the correct delay modelisation.

        Returns
        -------
        tf: np.array(..., dtype=np.complex)
            The complex open loop transfer function of the module.
        """
        module_delay = self._delay
        frequencies = np.array(frequencies, dtype=np.complex)
        # integrator with one cycle of extra delay
        tf = self. i /( frequencies *1j) \
             * np.exp(-1j * 8e-9 * self._frequency_correction *
                      frequencies * 2 * np.pi)
        # proportional (delay in self._delay included)
        tf += self.p
        # derivative action with one cycle of extra delay
        # if self.d != 0:
        #    tf += frequencies*1j/self.d \
        #          * np.exp(-1j * 8e-9 * self._frequency_correction *
        #                   frequencies * 2 * np.pi)
        # input filter modelisation
        for f in self.inputfilter:
            if f == 0:
                continue
            elif f > 0:  # lowpass
                tf /= (1.0 + 1j* frequencies / f)
                module_delay += 2  # two cycles extra delay per lowpass
            elif f < 0:  # highpass
                tf /= (1.0 + 1j * f / frequencies)
                # plus is correct here since f already has a minus sign
                module_delay += 1  # one cycle extra delay per highpass
        # add delay
        delay = module_delay * 8e-9 / self._frequency_correction + extradelay
        tf *= np.exp(-1j * delay * frequencies * 2 * np.pi)
        return tf

    normalization_on = BoolRegister(0x130, 0, doc="if True the PID is used "
                                                  "as a normalizer")

    # current normalization gain is p-register
    normalization_i = FloatRegister(0x10C, bits=_GAINBITS,
                                    norm=2 ** (_ISR) * 2.0 * np.pi *
                                         8e-9 / 2 ** 13 / 1.5625,
                                    # 1.5625 is empirical value,
                                    # no time/idea to do the maths
                                    doc="stablization crossover frequency [Hz]")

    @property
    def normalization_gain(self):
        """ current gain in the normalization """
        return self.p / 2.0

    normalization_inputoffset = FloatRegister(0x110, bits=(14 + _DSR),
                                              norm=2 ** (13 + _DSR),
                                              doc="normalization inputoffset [volts]")