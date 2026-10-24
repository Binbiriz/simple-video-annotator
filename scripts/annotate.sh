#!/usr/bin/env bash
# Render text and blur annotations onto a video with ffmpeg.
#
# usage: ./annotate.sh input.mp4 annotations.txt output.mp4
#
# Annotation file (one per line, '#' = comment):
#   text start end x y text...   draw text from start to end (seconds)
#   blur start end x y w h       blur a rectangle from start to end
# (a text line may omit the leading 'text' keyword)
# x/y of text lines may be ffmpeg expressions without spaces or commas,
# e.g. (w-text_w)/2  or  h-120.
#
# Environment overrides: FONT=/path/font.ttf  FONTSIZE=48
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 input.mp4 annotations.txt output.mp4" >&2
  exit 2
fi
in="$1"; list="$2"; out="$3"

font="${FONT:-$(fc-match -f '%{file}' sans 2>/dev/null || true)}"
[ -z "$font" ] && font=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
fontsize="${FONTSIZE:-48}"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

graph=""      # blur stages, joined with ';'
cur="0:v"     # label of the current video stream
texts=""      # drawtext filters, joined with ','
nb=0; nt=0

while IFS= read -r line; do
  [[ -z "${line//[[:space:]]/}" || "$line" == \#* ]] && continue
  if [[ "$line" == blur[[:space:]]* ]]; then
    read -r _ s e x y w h <<<"$line"
    nb=$((nb+1))
    stage="[$cur]split[a$nb][b$nb];"
    stage+="[b$nb]crop=$w:$h:$x:$y,boxblur=luma_radius=min(w\,h)/5:luma_power=3[bl$nb];"
    stage+="[a$nb][bl$nb]overlay=$x:$y:enable='between(t,$s,$e)'[v$nb]"
    graph="${graph:+$graph;}$stage"
    cur="v$nb"
  else
    if [[ "$line" == text[[:space:]]* ]]; then
      read -r _ s e x y text <<<"$line"
    else
      read -r s e x y text <<<"$line"   # legacy line without keyword
    fi
    nt=$((nt+1))
    printf '%s' "$text" > "$tmp/$nt.txt"   # own file: no escaping needed
    f="drawtext=fontfile=$font:textfile=$tmp/$nt.txt:expansion=none:fontsize=$fontsize"
    f+=":fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=12:x=$x:y=$y"
    f+=":enable='between(t,$s,$e)'"
    texts="${texts:+$texts,}$f"
  fi
done < "$list"

if [ "$nb" -eq 0 ] && [ "$nt" -eq 0 ]; then
  echo "No annotations found in $list" >&2
  exit 1
fi

if [ -n "$texts" ]; then
  graph="${graph:+$graph;}[$cur]$texts[vout]"
  cur="vout"
fi

ffmpeg -y -nostdin -hide_banner -stats -i "$in" \
  -filter_complex "$graph" -map "[$cur]" -map 0:a? -c:a copy "$out"
