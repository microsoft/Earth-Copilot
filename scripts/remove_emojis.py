"""
Temporary script to remove emojis from ALL code files in the repo.
Preserves emojis in files/lines that render in the actual app UI.
"""
import re
import os
from pathlib import Path

# Emoji regex pattern covering all common emoji ranges
EMOJI_PATTERN = re.compile(
    '['
    '\U0001F300-\U0001F9FF'  # Symbols & Pictographs, Emoticons, etc.
    '\U00002600-\U000027BF'  # Misc Symbols, Dingbats
    '\U0000FE0F'             # Variation Selector-16
    '\U0000200D'             # Zero Width Joiner
    ']+',
    flags=re.UNICODE
)

WORKSPACE = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# File extensions to scan
SCAN_EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.jsx', '.sh', '.md', '.ps1', '.yml', '.yaml'}

# Files where ALL emojis are UI-facing (skip entirely)
UI_ONLY_FILES = {
    'earth-copilot/web-ui/src/config/collectionConfig.ts',  # emoji: property values rendered in UI
    'earth-copilot/web-ui/src/ui/CatalogPanel.tsx',         # JSX heading with emoji
}

# Files with MIXED UI + non-UI emojis (selective stripping from console/logger/comment lines only)
MIXED_UI_FILES = {
    'earth-copilot/web-ui/src/components/Chat.tsx',
    'earth-copilot/web-ui/src/services/api.ts',
    'earth-copilot/web-ui/src/App.tsx',
    'earth-copilot/container-app/geoint/raster_data_fetcher.py',
}

# Skip these directories and files
SKIP_PATTERNS = {'__pycache__', 'node_modules', '.git', '.venv', 'venv', 'env',
                 'site-packages', 'dist', 'build', '.tox', '.mypy_cache',
                 'remove_emojis.py'}

def strip_emojis(text):
    """Remove all emoji characters from text."""
    return EMOJI_PATTERN.sub('', text)

def has_emojis(text):
    """Check if text contains any emojis."""
    return bool(EMOJI_PATTERN.search(text))

def process_full_strip(filepath):
    """Strip all emojis from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original = f.read()
    except (UnicodeDecodeError, PermissionError):
        return 0
    
    if not has_emojis(original):
        return 0
    
    cleaned = strip_emojis(original)
    count = len(EMOJI_PATTERN.findall(original))
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(cleaned)
    
    rel = filepath.relative_to(WORKSPACE)
    print(f"  CLEANED: {rel} ({count} emojis removed)")
    return count

def process_selective_strip(filepath):
    """Strip emojis only from console.log/warn/error, logger, and comment lines."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (UnicodeDecodeError, PermissionError):
        return 0
    
    count = 0
    new_lines = []
    for line in lines:
        stripped = line.strip()
        # Detect non-UI lines (console/logger/comment)
        is_console = any(kw in stripped for kw in ['console.log', 'console.warn', 'console.error'])
        is_comment_js = stripped.startswith('//')
        is_comment_py = stripped.startswith('#')
        is_logger = any(kw in stripped for kw in [
            'logger.info', 'logger.error', 'logger.warning', 'logger.debug',
            'logging.info', 'logging.warning', 'logging.error'
        ])
        
        if (is_console or is_comment_js or is_comment_py or is_logger) and has_emojis(line):
            count += len(EMOJI_PATTERN.findall(line))
            new_lines.append(strip_emojis(line))
        else:
            new_lines.append(line)
    
    if count > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        rel = filepath.relative_to(WORKSPACE)
        print(f"  CLEANED: {rel} ({count} emojis from non-UI lines)")
    return count

def should_skip(path):
    """Check if path should be skipped."""
    parts = path.parts
    for skip in SKIP_PATTERNS:
        if skip in parts or path.name == skip:
            return True
    return False

def get_relative(filepath):
    """Get relative path as forward-slash string."""
    return str(filepath.relative_to(WORKSPACE)).replace('\\', '/')

if __name__ == "__main__":
    print("=" * 60)
    print("Emoji Removal - Full Repo Scan")
    print("=" * 60)
    
    total = 0
    files_cleaned = 0
    files_skipped_ui = 0
    
    # Find all matching files
    all_files = []
    for ext in SCAN_EXTENSIONS:
        all_files.extend(WORKSPACE.rglob(f"*{ext}"))
    
    # Sort for deterministic output
    all_files.sort()
    
    for filepath in all_files:
        if should_skip(filepath):
            continue
        
        rel_path = get_relative(filepath)
        
        # Skip UI-only files
        if rel_path in UI_ONLY_FILES:
            files_skipped_ui += 1
            continue
        
        # Selective strip for mixed UI files
        if rel_path in MIXED_UI_FILES:
            removed = process_selective_strip(filepath)
            if removed > 0:
                total += removed
                files_cleaned += 1
            continue
        
        # Full strip for all other files
        removed = process_full_strip(filepath)
        if removed > 0:
            total += removed
            files_cleaned += 1
    
    print(f"\n{'=' * 60}")
    print(f"Files cleaned: {files_cleaned}")
    print(f"Files skipped (UI): {files_skipped_ui}")
    print(f"Total emojis removed: {total}")
    print("=" * 60)

def strip_emojis(text):
    """Remove all emoji characters from text."""
    return EMOJI_PATTERN.sub('', text)

if __name__ == "__main__":
    print("=" * 60)
    print("Emoji Removal - Full Repo Scan")
    print("=" * 60)
    
    total = 0
    files_cleaned = 0
    files_skipped_ui = 0
    
    # Find all matching files
    all_files = []
    for ext in SCAN_EXTENSIONS:
        all_files.extend(WORKSPACE.rglob(f"*{ext}"))
    
    # Sort for deterministic output
    all_files.sort()
    
    for filepath in all_files:
        if should_skip(filepath):
            continue
        
        rel_path = get_relative(filepath)
        
        # Skip UI-only files
        if rel_path in UI_ONLY_FILES:
            files_skipped_ui += 1
            continue
        
        # Selective strip for mixed UI files
        if rel_path in MIXED_UI_FILES:
            removed = process_selective_strip(filepath)
            if removed > 0:
                total += removed
                files_cleaned += 1
            continue
        
        # Full strip for all other files
        removed = process_full_strip(filepath)
        if removed > 0:
            total += removed
            files_cleaned += 1
    
    print(f"\n{'=' * 60}")
    print(f"Files cleaned: {files_cleaned}")
    print(f"Files skipped (UI): {files_skipped_ui}")
    print(f"Total emojis removed: {total}")
    print("=" * 60)
