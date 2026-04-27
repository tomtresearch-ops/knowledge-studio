#!/usr/bin/env python3
"""Archive unused prompt files, keeping only the active ones"""

import os
import shutil
from pathlib import Path

# Active prompts to keep
ACTIVE_PROMPTS = [
    'interview_prompt.txt',
    'genai_tools_prompt.txt',  # Note: code uses genai_tools, not tools
    'explainer_prompt.txt'
]

# Directories to process
CURRENT_BEST = Path('prompts/current_best')
ARCHIVE = Path('prompts/archive')
ROOT_PROMPTS = Path('prompts')

# Ensure archive exists
ARCHIVE.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("PROMPT FILES INSTRUCTORY")
print("=" * 60)

# List all files in current_best
print("\n📁 Files in prompts/current_best/:")
if CURRENT_BEST.exists():
    files = sorted([f.name for f in CURRENT_BEST.glob('*.txt')])
    for f in files:
        status = "✅ ACTIVE" if f in ACTIVE_PROMPTS else "📦 TO ARCHIVE"
        print(f"  {status}: {f}")
else:
    print("  Directory not found")

# List files in root prompts directory
print("\n📁 Files in prompts/ (root):")
if ROOT_PROMPTS.exists():
    files = sorted([f.name for f in ROOT_PROMPTS.glob('*.txt')])
    for f in files:
        print(f"  {f}")
else:
    print("  Directory not found")

# Check which active prompts exist
print("\n✅ ACTIVE PROMPTS STATUS:")
for prompt in ACTIVE_PROMPTS:
    in_current_best = (CURRENT_BEST / prompt).exists()
    in_root = (ROOT_PROMPTS / prompt).exists()
    if in_current_best:
        print(f"  ✓ {prompt} (in current_best/)")
    elif in_root:
        print(f"  ⚠ {prompt} (in root, should be in current_best/)")
    else:
        print(f"  ✗ {prompt} (NOT FOUND)")

print("\n" + "=" * 60)
print("ARCHIVING UNUSED PROMPTS")
print("=" * 60)

# Archive files from current_best
if CURRENT_BEST.exists():
    files_to_archive = []
    for f in CURRENT_BEST.glob('*.txt'):
        if f.name not in ACTIVE_PROMPTS:
            files_to_archive.append(f)
    
    if files_to_archive:
        print(f"\n📦 Moving {len(files_to_archive)} files to archive...")
        for f in files_to_archive:
            dest = ARCHIVE / f.name
            # Handle duplicates by adding number
            counter = 1
            while dest.exists():
                stem = f.stem
                dest = ARCHIVE / f"{stem}_{counter}{f.suffix}"
                counter += 1
            shutil.move(str(f), str(dest))
            print(f"  ✓ Moved: {f.name} → archive/{dest.name}")
    else:
        print("\n  (no files to archive)")

# Also archive files from root prompts directory (except active ones)
if ROOT_PROMPTS.exists():
    root_files_to_archive = []
    for f in ROOT_PROMPTS.glob('*.txt'):
        if f.name not in ACTIVE_PROMPTS and f.name not in ['youtube_summary.txt']:
            root_files_to_archive.append(f)
    
    if root_files_to_archive:
        print(f"\n📦 Moving {len(root_files_to_archive)} files from root to archive...")
        for f in root_files_to_archive:
            dest = ARCHIVE / f.name
            counter = 1
            while dest.exists():
                stem = f.stem
                dest = ARCHIVE / f"{stem}_{counter}{f.suffix}"
                counter += 1
            shutil.move(str(f), str(dest))
            print(f"  ✓ Moved: {f.name} → archive/{dest.name}")

print("\n" + "=" * 60)
print("FINAL STATUS")
print("=" * 60)

print("\n✅ ACTIVE PROMPTS (kept in current_best/):")
if CURRENT_BEST.exists():
    for prompt in ACTIVE_PROMPTS:
        if (CURRENT_BEST / prompt).exists():
            print(f"  ✓ {prompt}")
        else:
            print(f"  ✗ {prompt} (MISSING!)")

print("\n📦 ARCHIVED PROMPTS:")
if ARCHIVE.exists():
    archived = sorted([f.name for f in ARCHIVE.glob('*.txt')])
    if archived:
        for f in archived:
            print(f"  📦 {f}")
    else:
        print("  (none)")

