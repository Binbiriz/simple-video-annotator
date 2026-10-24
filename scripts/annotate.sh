#!/usr/bin/env bash
# Render text and blur annotations onto a video with ffmpeg.
#
# usage: ./annotate.sh input.mp4 annotations.txt output.mp4
#
# Annotation file (one per line, '#' = comment):
#   text|start|end|x|y|w|h|size|boxcolor|textcolor|text
#                                draw text inside the box from start to end (seconds);
#                                the text is the rest of the line and may contain '|'
#   blur|start|end|x|y|w|h       blur a rectangle from start to end
# Whitespace around fields is ignored; x/y/w/h are whole video pixels. size is the font size
# in px (8-72). boxcolor is #rrggbb (the '#' is optional), drawn at 50% opacity; textcolor
# is #000000 or #ffffff. Older text line shapes are no longer supported.
#
# Text is drawn left aligned in a monospace font (Ubuntu Mono preferred), wrapped to the box
# width and drawn at exactly the given size (no auto-fit). If the wrapped text is taller than
# the box, or not even one character fits its width, a warning is printed and the text is
# drawn anyway. The layout mirrors src/vidnote/textfit.py: keep the constants in sync.
#
# Environment overrides: FONT=/path/font.ttf
# Test hook: VIDNOTE_PRINT_LAYOUT=1 prints the layout of each text line and exits before
# running ffmpeg.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 input.mp4 annotations.txt output.mp4" >&2
  exit 2
fi
in="$1"; list="$2"; out="$3"

# count characters, not bytes, so the layout matches the Python implementation
locales="$(locale -a 2>/dev/null || true)"
for l in C.UTF-8 C.utf8 en_US.UTF-8 en_US.utf8; do
  if [[ $'\n'"$locales"$'\n' == *$'\n'"$l"$'\n'* ]]; then export LC_ALL="$l"; break; fi
done

# keep in sync with textfit.py; ADV_PM is the glyph advance in per mille of the font size,
# deliberately a bit wide so every common monospace font fits (Ubuntu Mono is ~560)
MIN_SIZE=8; MAX_SIZE=72; PAD=4; LINE_H_PM=1150; ADV_PM=605
font="${FONT:-}"
if [ -z "$font" ]; then
  um="$(fc-match -f '%{family}|%{file}' 'Ubuntu Mono' 2>/dev/null || true)"
  if [[ "${um%%|*}" == "Ubuntu Mono" ]]; then
    font="${um#*|}"
  else
    echo "warning: Ubuntu Mono not found, using a fallback monospace font" >&2
    font="$(fc-match -f '%{file}' monospace 2>/dev/null || true)"
  fi
fi
[ -z "$font" ] && font=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

graph=""      # blur stages, joined with ';'
cur="0:v"     # label of the current video stream
texts=""      # drawtext filters, joined with ','
nb=0; nt=0; nl=0
boxes=()     # text boxes as lineno:x:y:w:h, checked against the frame

trim() {
  local v="$1"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  printf '%s' "$v"
}
die() { echo "$list:$lineno: $1: $raw" >&2; exit 1; }

# toint: decimal value of an integer field (so 08 is not read as octal)
toint() {
  local v="$1"
  if [[ "$v" == -* ]]; then echo $(( -(10#${v#-}) )); else echo $(( 10#$v )); fi
}

# pop_field: move the first '|'-separated field of $rest into $field
pop_field() {
  if [[ "$rest" == *"|"* ]]; then
    field="$(trim "${rest%%|*}")"; rest="${rest#*|}"
  else
    field="$(trim "$rest")"; rest=""
  fi
}

# wrap_text cols: greedy word wrap of $text into the array $wrapped (mirrors textfit.wrap)
wrap_text() {
  local cols="$1" word cur=""
  local -a words
  wrapped=()
  read -ra words <<< "$text"
  for word in "${words[@]}"; do
    while [ "${#word}" -gt "$cols" ]; do
      if [ -n "$cur" ]; then wrapped+=("$cur"); cur=""; fi
      wrapped+=("${word:0:cols}")
      word="${word:cols}"
    done
    if [ -z "$cur" ]; then
      cur="$word"
    elif [ $(( ${#cur} + 1 + ${#word} )) -le "$cols" ]; then
      cur+=" $word"
    else
      wrapped+=("$cur"); cur="$word"
    fi
  done
  if [ -n "$cur" ]; then wrapped+=("$cur"); fi
}

# layout_text size w h: wrap $text into a w x h box at the given font size (mirrors
# textfit.layout_text). Sets $layout_ok (1 = fits) and the array $wrapped.
layout_text() {
  local size="$1" avail_w=$(( $2 - 2 * PAD )) avail_h=$(( $3 - 2 * PAD )) cols line_h
  if [ "$avail_w" -lt 0 ]; then avail_w=0; fi
  cols=$(( avail_w * 1000 / (size * ADV_PM) ))
  if [ "$cols" -lt 1 ]; then cols=1; fi
  wrap_text "$cols"
  line_h=$(( size * LINE_H_PM / 1000 ))
  layout_ok=0
  if [ $(( ${#wrapped[@]} * line_h )) -le "$avail_h" ] \
     && [ "$avail_w" -ge $(( size * ADV_PM / 1000 )) ]; then
    layout_ok=1
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
    msg="text lines need: text|start|end|x|y|w|h|size|boxcolor|textcolor|text (older text formats are no longer supported)"
    [ "${#pipes}" -ge 10 ] || die "$msg"
    pop_field; s="$field"; pop_field; e="$field"
    pop_field; x="$field"; pop_field; y="$field"
    pop_field; w="$field"; pop_field; h="$field"
    pop_field; size="$field"; pop_field; boxcolor="$field"; pop_field; textcolor="$field"
    text="$(trim "$rest")"
    [[ "$s" =~ ^[0-9]+(\.[0-9]+)?$ && "$e" =~ ^[0-9]+(\.[0-9]+)?$ ]] \
      || die "start and end must be numbers"
    [[ "$x" =~ ^-?[0-9]+$ && "$y" =~ ^-?[0-9]+$ && "$w" =~ ^[0-9]+$ && "$h" =~ ^[0-9]+$ ]] \
      || die "x, y, w and h must be whole numbers; $msg"
    [[ "$size" =~ ^[0-9]+$ ]] || die "size must be a whole number; $msg"
    x="$(toint "$x")"; y="$(toint "$y")"; w="$(toint "$w")"; h="$(toint "$h")"
    size="$(toint "$size")"
    [ "$w" -gt 0 ] && [ "$h" -gt 0 ] || die "w and h must be greater than 0"
    [ "$size" -ge "$MIN_SIZE" ] && [ "$size" -le "$MAX_SIZE" ] \
      || die "size must be between $MIN_SIZE and $MAX_SIZE"
    [[ "$boxcolor" =~ ^#?[0-9a-fA-F]{6}$ ]] || die "box colour must be 6 hex digits like #1e90ff"
    boxcolor="${boxcolor#\#}"; boxcolor="${boxcolor,,}"
    [[ "$textcolor" =~ ^#?[0-9a-fA-F]{6}$ ]] || die "text colour must be #000000 or #ffffff"
    textcolor="${textcolor#\#}"; textcolor="${textcolor,,}"
    [ "$textcolor" = 000000 ] || [ "$textcolor" = ffffff ] \
      || die "text colour must be #000000 or #ffffff"
    [ -n "$text" ] || die "text is empty"
    nt=$((nt+1))
    layout_text "$size" "$w" "$h"
    if [ "$layout_ok" -ne 1 ]; then
      echo "warning: $list:$lineno: text does not fit in ${w}x${h} at ${size}px, drawing it anyway" >&2
    fi
    if [ -n "${VIDNOTE_PRINT_LAYOUT:-}" ]; then
      echo "layout|$lineno|$size|$layout_ok|0x$boxcolor|0x$textcolor"
      printf '  |%s\n' "${wrapped[@]}"
    fi
    boxes+=("$lineno:$x:$y:$w:$h")
    f="drawbox=x=$x:y=$y:w=$w:h=$h:color=0x$boxcolor@0.5:t=fill:enable='between(t,$s,$e)'"
    line_h=$(( size * LINE_H_PM / 1000 ))
    for i in "${!wrapped[@]}"; do   # one drawtext per line: exact, font-independent pitch
      nl=$((nl+1))
      printf '%s' "${wrapped[$i]}" > "$tmp/$nl.txt"   # own file: no escaping needed
      f+=",drawtext=fontfile='$font':textfile=$tmp/$nl.txt:expansion=none:fontsize=$size"
      f+=":fontcolor=0x$textcolor:x=$((x+PAD)):y=$((y+PAD+i*line_h))"
      f+=":enable='between(t,$s,$e)'"
    done
    texts="${texts:+$texts,}$f"
  else
    die "unrecognized line (expected text|... or blur|...)"
  fi
done < "$list"

if [ "$nb" -eq 0 ] && [ "$nt" -eq 0 ]; then
  echo "No annotations found in $list" >&2
  exit 1
fi

if [ -n "${VIDNOTE_PRINT_LAYOUT:-}" ]; then exit 0; fi

if [ "${#boxes[@]}" -gt 0 ] && command -v ffprobe >/dev/null 2>&1; then
  wh="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height \
        -of csv=p=0:s=x "$in" 2>/dev/null || true)"
  if [[ "$wh" =~ ^[0-9]+x[0-9]+$ ]]; then
    vw="${wh%x*}"; vh="${wh#*x}"
    for b in "${boxes[@]}"; do
      IFS=: read -r bl bx by bw bh <<< "$b"
      if [ "$bx" -lt 0 ] || [ "$by" -lt 0 ] || [ $((bx + bw)) -gt "$vw" ] \
         || [ $((by + bh)) -gt "$vh" ]; then
        echo "$list:$bl: text box extends beyond the ${vw}x${vh} video" >&2
        exit 1
      fi
    done
  fi
fi

if [ -n "$texts" ]; then
  graph="${graph:+$graph;}[$cur]$texts[vout]"
  cur="vout"
fi

ffmpeg -y -nostdin -hide_banner -stats -i "$in" \
  -filter_complex "$graph" -map "[$cur]" -map 0:a? -c:a copy "$out"
