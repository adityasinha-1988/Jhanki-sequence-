"""
mcp23017.py — minimal MicroPython driver for the MCP23017 16-bit I2C GPIO
expander. Only what this project needs: set all pins as outputs, and drive
individual pins HIGH/LOW. IOCON.BANK is assumed at its power-on default (0),
so register addresses are sequential (GPIOA=0x12, GPIOB=0x13, etc.).
"""

_IODIRA = 0x00
_IODIRB = 0x01
_GPPUA = 0x0C   # pull-up resistors (not used, kept for reference)
_GPPUB = 0x0D
_GPIOA = 0x12
_GPIOB = 0x13
_OLATA = 0x14
_OLATB = 0x15


class MCP23017:
    def __init__(self, i2c, address=0x20):
        self.i2c = i2c
        self.address = address
        # Shadow registers for the two output latches (bits we've last written).
        self._olat_a = 0x00
        self._olat_b = 0x00

    def _write_reg(self, reg, value):
        self.i2c.writeto_mem(self.address, reg, bytes([value & 0xFF]))

    def _read_reg(self, reg):
        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def set_all_outputs(self):
        """Configure all 16 pins (GPA0-7, GPB0-7) as outputs and drive them low."""
        self._write_reg(_IODIRA, 0x00)  # 0 = output
        self._write_reg(_IODIRB, 0x00)
        self._olat_a = 0x00
        self._olat_b = 0x00
        self._write_reg(_OLATA, self._olat_a)
        self._write_reg(_OLATB, self._olat_b)

    def set_pin(self, pin, value):
        """
        pin: 0-15  (0-7 = GPA0-GPA7, 8-15 = GPB0-GPB7)
        value: 0 or 1
        """
        if not 0 <= pin <= 15:
            raise ValueError("pin must be 0-15")

        if pin < 8:
            bit = pin
            if value:
                self._olat_a |= (1 << bit)
            else:
                self._olat_a &= ~(1 << bit)
            self._write_reg(_OLATA, self._olat_a)
        else:
            bit = pin - 8
            if value:
                self._olat_b |= (1 << bit)
            else:
                self._olat_b &= ~(1 << bit)
            self._write_reg(_OLATB, self._olat_b)

    def all_off(self):
        self._olat_a = 0x00
        self._olat_b = 0x00
        self._write_reg(_OLATA, self._olat_a)
        self._write_reg(_OLATB, self._olat_b)
