#!/usr/bin/env bash
# Render text and blur annotations onto a video with ffmpeg.
#
# usage: ./annotate.sh input.mp4 annotations.txt output.mp4
#
# Annotation file (one per line, '#' = comment):
#   text|start|end|x|y|text   draw text from start to end (seconds); text may contain '|'
#   blur|start|end|x|y|w|h    blur a rectangle from start to end
# Whitespace around fields is ignored; x/y/w/h are whole video pixels.
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

trim() {
  local v="$1"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  printf '%s' "$v"
}
die() { echo "$list:$lineno: $1: $raw" >&2; exit 1; }

# pop_field: move the first '|'-separated field of $rest into $field
pop_field() {
  if [[ "$rest" == *"|"* ]]; then
    field="$(trim "${rest%%|*}")"; rest="${rest#*|}"
  else
    field="$(trim "$rest")"; rest=""
  fi
}

lineno=0
while IFS= read -r line || [ -n "$line" ]; do
  lineno=$((lineno+1))
  line="${line%$'\r'}"
  raw="$line"
  [[ -z "${line//[[:space:]]/}" || "$(trim "$line")" == \#* ]] && continue
  pipes="${line//[^|]/}"
  rest="$line"
  pop_field; kind="$field"
  if [ "$kind" = blur ]; then
    [ "${#pipes}" -eq 6 ] || die "blur lines need: blur|start|end|x|y|w|h"
    pop_field; s="$field"; pop_field; e="$field"
    pop_field; x="$field"; pop_field; y="$field"
    pop_field; w="$field"; pop_field; h="$field"
    [[ "$s" =~ ^[0-9]+(\.[0-9]+)?$ && "$e" =~ ^[0-9]+(\.[0-9]+)?$ ]] \
      || die "start and end must be numbers"
    [[ "$x" =~ ^-?[0-9]+$ && "$y" =~ ^-?[0-9]+$ && "$w" =~ ^-?[0-9]+$ && "$h" =~ ^-?[0-9]+$ ]] \
      || die "x, y, w and h must be whole numbers"
    nb=$((nb+1))
    stage="[$cur]split[a$nb][b$nb];"
    stage+="[b$nb]crop=$w:$h:$x:$y,boxblur=luma_radius=min(w\,h)/5:luma_power=3[bl$nb];"
    stage+="[a$nb][bl$nb]overlay=$x:$y:enable='between(t,$s,$e)'[v$nb]"
    graph="${graph:+$graph;}$stage"
    cur="v$nb"
  elif [ "$kind" = text ]; then
    [ "${#pipes}" -ge 5 ] || die "text lines need: text|start|end|x|y|text"
    pop_field; s="$field"; pop_field; e="$field"
    pop_field; x="$field"; pop_field; y="$field"
    text="$(trim "$rest")"
    [[ "$s" =~ ^[0-9]+(\.[0-9]+)?$ && "$e" =~ ^[0-9]+(\.[0-9]+)?$ ]] \
      || die "start and end must be numbers"
    [[ "$x" =~ ^-?[0-9]+$ && "$y" =~ ^-?[0-9]+$ ]] || die "x and y must be whole numbers"
    [ -n "$text" ] || die "text is empty"
    nt=$((nt+1))
    printf '%s' "$text" > "$tmp/$nt.txt"   # own file: no escaping needed
    f="drawtext=fontfile=$font:textfile=$tmp/$nt.txt:expansion=none:fontsize=$fontsize"
    f+=":fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=12:x=$x:y=$y"
    f+=":enable='between(t,$s,$e)'"
    texts="${texts:+$texts,}$f"
  else
    die "unrecognized line (expected text|... or blur|...)"
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
