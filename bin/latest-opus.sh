#!/bin/bash
# latest-opus.sh
# Prints the path to the most recently received WhatsApp voice note (.opus)
# found in the macOS WhatsApp app container. Used as a fallback trigger.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
BASE="$HOME/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/Message/Media"
[ -d "$BASE" ] || { echo "" ; exit 0; }
find "$BASE" -type f -iname '*.opus' -print0 2>/dev/null \
  | xargs -0 stat -f '%m %N' 2>/dev/null \
  | sort -rn | head -1 | cut -d' ' -f2-
