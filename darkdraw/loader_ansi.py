import re

from visidata import VisiData, vd, AttrDict
from .drawing import Drawing, DrawingSheet


class ANSIParser:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.fg_color = None
        self.bg_color = None
        self.bold = False
        self.underline = False
        self.reverse = False
        self.rows = []
        self.max_x = 0
        self.max_y = 0
    
    def rgb_to_256(self, r, g, b):
        'Convert RGB to nearest 256 color index.'
        # Handle grayscale
        if r == g == b:
            if r < 8:
                return 16
            if r > 248:
                return 231
            return round(((r - 8) / 247) * 24) + 232
        
        # Handle colors - map to 6x6x6 color cube
        r6 = round(r / 51)
        g6 = round(g / 51)
        b6 = round(b / 51)
        
        return 16 + (36 * r6) + (6 * g6) + b6
        
    def parse(self, content):
        # ANSI escape sequence patterns
        csi_pattern = re.compile(r'\x1b\[([0-9;:]*)([A-Za-z])')  # CSI sequences (including malformed with colons)
        osc_pattern = re.compile(r'\x1b\]([^\x07\x1b]*(?:\x07|\x1b\\))')  # OSC sequences
        charset_pattern = re.compile(r'\x1b[()][AB012]')  # Character set selection
        
        i = 0
        
        while i < len(content):
            # Look for CSI escape sequence
            match = csi_pattern.match(content, i)
            if match:
                # Replace colons with semicolons for malformed RGB sequences
                params_str = match.group(1).replace(':', ';')
                params = params_str.split(';') if params_str else ['']
                command = match.group(2)
                self.handle_escape_sequence(params, command)
                i = match.end()
                continue
            
            # Skip OSC sequences (window title, etc.)
            match = osc_pattern.match(content, i)
            if match:
                i = match.end()
                continue
            
            # Skip charset selection sequences
            match = charset_pattern.match(content, i)
            if match:
                i = match.end()
                continue
            
            # Regular character
            ch = content[i]
            if ch == '\n':
                self.y += 1
                self.x = 0
            elif ch == '\r':
                self.x = 0
            elif ch != '\x1b':  # Any non-escape character
                # Handle both ASCII and Unicode characters
                if ord(ch) >= 32 or ch in '\t':  # Printable or tab
                    self.add_character(ch)
                    self.x += 1
            i += 1
        
        return self.rows
    
    def handle_escape_sequence(self, params, command):
        if command == 'm':  # SGR - Select Graphic Rendition
            self.handle_sgr(params)
        elif command == 'H' or command == 'f':  # Cursor position
            try:
                y = int(params[0]) - 1 if params[0] else 0
                x = int(params[1]) - 1 if len(params) > 1 and params[1] else 0
                self.x = max(0, x)
                self.y = max(0, y)
            except (ValueError, IndexError):
                pass
        elif command == 'J':  # Clear screen
            if params and params[0] == '2':
                # Clear entire screen - we just reset position
                self.x = 0
                self.y = 0
        elif command == 'C':  # Cursor forward
            try:
                n = int(params[0]) if params[0] else 1
                self.x += n
            except ValueError:
                pass
        elif command == 'D':  # Cursor backward
            try:
                n = int(params[0]) if params[0] else 1
                self.x = max(0, self.x - n)
            except ValueError:
                pass
        elif command == 'A':  # Cursor up
            try:
                n = int(params[0]) if params[0] else 1
                self.y = max(0, self.y - n)
            except ValueError:
                pass
        elif command == 'B':  # Cursor down
            try:
                n = int(params[0]) if params[0] else 1
                self.y += n
            except ValueError:
                pass
    
    def handle_sgr(self, params):
        for param in params:
            if not param:
                param = '0'
            try:
                code = int(param)
            except ValueError:
                continue
            
            if code == 0:  # Reset
                self.fg_color = None
                self.bg_color = None
                self.bold = False
                self.underline = False
                self.reverse = False
            elif code == 1:  # Bold
                self.bold = True
            elif code == 4:  # Underline
                self.underline = True
            elif code == 7:  # Reverse
                self.reverse = True
            elif code == 22:  # Normal intensity
                self.bold = False
            elif code == 24:  # No underline
                self.underline = False
            elif code == 27:  # No reverse
                self.reverse = False
            elif 30 <= code <= 37:  # Standard foreground colors
                self.fg_color = code - 30
            elif code == 38:  # Extended foreground color
                # Need to check next parameters
                idx = params.index(str(code))
                if idx + 1 < len(params):
                    if params[idx + 1] == '5' and idx + 2 < len(params):
                        # 256 color mode
                        try:
                            self.fg_color = int(params[idx + 2]) if params[idx + 2] else None
                        except (ValueError, IndexError):
                            pass
                    elif params[idx + 1] == '2':
                        # RGB/truecolor mode - we'll approximate to 256 colors
                        if idx + 4 < len(params):
                            try:
                                r = int(params[idx + 2]) if params[idx + 2] else 153
                                g = int(params[idx + 3]) if params[idx + 3] else 153
                                b = int(params[idx + 4]) if params[idx + 4] else 153
                            except (ValueError, IndexError):
                                r = g = b = 153
                            # Convert RGB to nearest 256 color
                            self.fg_color = self.rgb_to_256(r, g, b)
            elif code == 39:  # Default foreground
                self.fg_color = None
            elif 40 <= code <= 47:  # Standard background colors
                self.bg_color = code - 40
            elif code == 48:  # Extended background color
                # Need to check next parameters
                idx = params.index(str(code))
                if idx + 1 < len(params):
                    if params[idx + 1] == '5' and idx + 2 < len(params):
                        # 256 color mode
                        try:
                            self.bg_color = int(params[idx + 2]) if params[idx + 2] else None
                        except (ValueError, IndexError):
                            pass
                    elif params[idx + 1] == '2':
                        # RGB/truecolor mode - we'll approximate to 256 colors
                        if idx + 4 < len(params):
                            try:
                                r = int(params[idx + 2]) if params[idx + 2] else 153
                                g = int(params[idx + 3]) if params[idx + 3] else 153
                                b = int(params[idx + 4]) if params[idx + 4] else 153
                            except (ValueError, IndexError):
                                r = g = b = 153
                            # Convert RGB to nearest 256 color
                            self.bg_color = self.rgb_to_256(r, g, b)
            elif code == 49:  # Default background
                self.bg_color = None
            elif 90 <= code <= 97:  # Bright foreground colors
                self.fg_color = code - 90 + 8
            elif 100 <= code <= 107:  # Bright background colors
                self.bg_color = code - 100 + 8
    
    def add_character(self, ch):
        # Build color string in DarkDraw format
        color_parts = []
        
        if self.bold:
            color_parts.append('bold')
        if self.underline:
            color_parts.append('underline')
        
        # Handle reverse video
        fg = self.fg_color
        bg = self.bg_color
        if self.reverse:
            fg, bg = bg, fg
        
        if fg is not None:
            color_parts.append(str(fg))
        
        if bg is not None:
            color_parts.append('on')
            color_parts.append(str(bg))
        
        color = ' '.join(color_parts) if color_parts else ''
        
        # Create row
        row = AttrDict(type='', x=self.x, y=self.y, text=ch, color=color, tags=[])
        
        self.rows.append(row)
        
        # Track dimensions
        self.max_x = max(self.max_x, self.x)
        self.max_y = max(self.max_y, self.y)


@VisiData.api
def open_ansi(vd, p):
    return open_ans(vd, p)


@VisiData.api
def open_ans(vd, p):
    'Open ANSI art files (.ans, .ansi).'
    content = p.read_bytes()
    
    # Try different encodings - prioritize UTF-8 for modern captures
    text = None
    for encoding in ['utf-8', 'cp437', 'latin-1']:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    
    if text is None:
        text = content.decode('utf-8', errors='replace')
        vd.warning(f'Using UTF-8 with replacement for {p.name}')
    
    # Parse ANSI sequences
    parser = ANSIParser()
    rows = parser.parse(text)
    
    sheet = DrawingSheet(p.name, rows=rows)
    return Drawing(p.name, source=sheet)