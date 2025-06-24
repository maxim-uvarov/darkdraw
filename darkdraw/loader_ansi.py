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
        
    def parse(self, content):
        # ANSI escape sequence patterns
        csi_pattern = re.compile(r'\x1b\[([0-9;]*)([A-Za-z])')  # CSI sequences
        osc_pattern = re.compile(r'\x1b\]([^\x07\x1b]*(?:\x07|\x1b\\))')  # OSC sequences
        charset_pattern = re.compile(r'\x1b[()][AB012]')  # Character set selection
        
        i = 0
        
        while i < len(content):
            # Look for CSI escape sequence
            match = csi_pattern.match(content, i)
            if match:
                params = match.group(1).split(';') if match.group(1) else ['']
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
            y = int(params[0]) - 1 if params[0] else 0
            x = int(params[1]) - 1 if len(params) > 1 and params[1] else 0
            self.x = x
            self.y = y
        elif command == 'J':  # Clear screen
            if params[0] == '2':
                # Clear entire screen - we just reset position
                self.x = 0
                self.y = 0
        elif command == 'C':  # Cursor forward
            n = int(params[0]) if params[0] else 1
            self.x += n
        elif command == 'D':  # Cursor backward
            n = int(params[0]) if params[0] else 1
            self.x = max(0, self.x - n)
        elif command == 'A':  # Cursor up
            n = int(params[0]) if params[0] else 1
            self.y = max(0, self.y - n)
        elif command == 'B':  # Cursor down
            n = int(params[0]) if params[0] else 1
            self.y += n
    
    def handle_sgr(self, params):
        for param in params:
            if not param:
                param = '0'
            code = int(param)
            
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
                if idx + 2 < len(params) and params[idx + 1] == '5':
                    self.fg_color = int(params[idx + 2])
            elif code == 39:  # Default foreground
                self.fg_color = None
            elif 40 <= code <= 47:  # Standard background colors
                self.bg_color = code - 40
            elif code == 48:  # Extended background color
                # Need to check next parameters
                idx = params.index(str(code))
                if idx + 2 < len(params) and params[idx + 1] == '5':
                    self.bg_color = int(params[idx + 2])
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
        row = AttrDict(
            type='',
            x=self.x,
            y=self.y,
            text=ch,
            color=color,
            tags=[]
        )
        
        self.rows.append(row)
        
        # Track dimensions
        self.max_x = max(self.max_x, self.x)
        self.max_y = max(self.max_y, self.y)


@VisiData.api
def open_ansi(vd, p):
    return open_ans(vd, p)


@VisiData.api
def open_ans(vd, p):
    """Open ANSI art files (.ans, .ansi)"""
    content = p.read_bytes()
    
    # Try different encodings - prioritize UTF-8 for modern captures
    for encoding in ['utf-8', 'cp437', 'latin-1']:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        # Default to utf-8 with error handling
        text = content.decode('utf-8', errors='replace')
    
    # Parse ANSI sequences
    parser = ANSIParser()
    rows = parser.parse(text)
    
    # Create DrawingSheet
    sheet = DrawingSheet(p.name, rows=rows)
    
    # Return Drawing instance
    return Drawing(p.name, source=sheet)