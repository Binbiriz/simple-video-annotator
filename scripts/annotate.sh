#!/usr/bin/env bash
# Render text, blur and arrow annotations onto a video with ffmpeg.
#
# usage: ./annotate.sh input.mp4 annotations.txt output.mp4
#
# Annotation file (one per line, '#' = comment):
#   text|start|end|x|y|w|h|size|boxcolor|textcolor|text
#                                draw text inside the box from start to end (seconds);
#                                the text is the rest of the line and may contain '|'
#   blur|start|end|x|y|w|h       blur a rectangle from start to end
#   arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle
#                                draw a straight arrow from (x1,y1) to (x2,y2) from start to end
# Whitespace around fields is ignored; x/y/w/h and the arrow points are whole video pixels.
# size is the font size in px (8-72). boxcolor is #rrggbb (the '#' is optional), drawn at 50%
# opacity; textcolor is #000000 or #ffffff. Older text line shapes are no longer supported.
# An arrow has a thickness of 1-30 px, a colour #rrggbb (drawn at 50% opacity, the whole arrow
# as one shape) and a style for each end: none or arrow (an arrowhead). Both end points must
# lie inside the video. Annotations are drawn in file order (later lines on top).
#
# Text is drawn left aligned in a monospace font (Ubuntu Mono preferred), wrapped to the box
# width and drawn at exactly the given size (no auto-fit). If the wrapped text is taller than
# the box, or not even one character fits its width, a warning is printed and the text is
# drawn anyway. The layout mirrors src/vidnote/textfit.py: keep the constants in sync.
#
# Each arrow is drawn as a transparent PNG made by ffmpeg itself (the geq filter computes an
# anti-aliased alpha mask), laid over the video during its time range. The geometry mirrors
# src/vidnote/arrowgeom.py: keep the constants and formulas in sync.
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
# arrows, keep in sync with arrowgeom.py: head length 4*t+6, head half-width 2*t+3,
# overlay padding (half-width + 2), fixed alpha 128 of 255
MIN_THICK=1; MAX_THICK=30; HEAD_LEN_K=4; HEAD_LEN_ADD=6; HEAD_HALF_K=2; HEAD_HALF_ADD=3
ARROW_ALPHA=128
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

graph=""      # filter stages (blur, text, arrow) in file order, joined with ';'
cur="0:v"     # label of the current video stream
nb=0; nt=0; na=0; nl=0
boxes=()     # text boxes as lineno:x:y:w:h, checked against the frame
points=()    # arrow end points as lineno:x1:y1:x2:y2, checked against the frame
arrows=()    # arrows as lineno:x1:y1:x2:y2:thickness:color:startstyle:endstyle

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
    graph="${graph:+$graph;}[$cur]$f[t$nt]"
    cur="t$nt"
  elif [ "$kind" = arrow ]; then
    [ "${#pipes}" -eq 10 ] \
      || die "arrow lines need: arrow|start|end|x1|y1|x2|y2|thickness|color|startstyle|endstyle"
    pop_field; s="$field"; pop_field; e="$field"
    pop_field; x="$field"; pop_field; y="$field"
    pop_field; x2="$field"; pop_field; y2="$field"
    pop_field; thick="$field"; pop_field; color="$field"
    pop_field; ss="${field,,}"; pop_field; es="${field,,}"
    [[ "$s" =~ ^[0-9]+(\.[0-9]+)?$ && "$e" =~ ^[0-9]+(\.[0-9]+)?$ ]] \
      || die "start and end must be numbers"
    [[ "$x" =~ ^-?[0-9]+$ && "$y" =~ ^-?[0-9]+$ && "$x2" =~ ^-?[0-9]+$ && "$y2" =~ ^-?[0-9]+$ ]] \
      || die "x1, y1, x2 and y2 must be whole numbers"
    [[ "$thick" =~ ^[0-9]+$ ]] || die "thickness must be a whole number"
    x="$(toint "$x")"; y="$(toint "$y")"; x2="$(toint "$x2")"; y2="$(toint "$y2")"
    thick="$(toint "$thick")"
    [ "$x" -ne "$x2" ] || [ "$y" -ne "$y2" ] || die "start and end points must differ"
    [ "$thick" -ge "$MIN_THICK" ] && [ "$thick" -le "$MAX_THICK" ] \
      || die "thickness must be between $MIN_THICK and $MAX_THICK"
    [[ "$color" =~ ^#?[0-9a-fA-F]{6}$ ]] || die "colour must be 6 hex digits like #1e90ff"
    color="${color#\#}"; color="${color,,}"
    for style in "$ss" "$es"; do
      [ "$style" = none ] || [ "$style" = arrow ] \
        || die "unknown end style '$style'; expected none or arrow"
    done
    na=$((na+1))
    points+=("$lineno:$x:$y:$x2:$y2")
    pad=$(( HEAD_HALF_K * thick + HEAD_HALF_ADD + 2 ))
    # overlay rounds its position down to even coordinates on yuv420p video; do it here so the
    # image is drawn relative to the position that is really used
    ox=$(( ((x < x2 ? x : x2) - pad) >> 1 << 1 )); oy=$(( ((y < y2 ? y : y2) - pad) >> 1 << 1 ))
    arrows+=("$lineno:$x:$y:$x2:$y2:$thick:$color:$ss:$es:$ox:$oy")
    stage="[$cur][$na:v]overlay=$ox:$oy:enable='between(t,$s,$e)':shortest=1[ar$na]"
    graph="${graph:+$graph;}$stage"
    cur="ar$na"
  else
    die "unrecognized line (expected text|..., blur|... or arrow|...)"
  fi
done < "$list"

if [ "$nb" -eq 0 ] && [ "$nt" -eq 0 ] && [ "$na" -eq 0 ]; then
  echo "No annotations found in $list" >&2
  exit 1
fi

if [ -n "${VIDNOTE_PRINT_LAYOUT:-}" ]; then exit 0; fi

if { [ "${#boxes[@]}" -gt 0 ] || [ "${#points[@]}" -gt 0 ]; } && command -v ffprobe >/dev/null 2>&1; then
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
    for p in "${points[@]+"${points[@]}"}"; do
      IFS=: read -r pl px1 py1 px2 py2 <<< "$p"
      if [ "$px1" -lt 0 ] || [ "$py1" -lt 0 ] || [ "$px2" -lt 0 ] || [ "$py2" -lt 0 ] \
         || [ "$px1" -gt "$vw" ] || [ "$px2" -gt "$vw" ] \
         || [ "$py1" -gt "$vh" ] || [ "$py2" -gt "$vh" ]; then
        echo "$list:$pl: arrow end point outside the ${vw}x${vh} video" >&2
        exit 1
      fi
    done
  fi
fi

# head_cov s: coverage expression of an arrowhead whose tip is at distance s along the axis
head_cov() {
  local s="$1"
  echo "clip(min(min(($s)+0.5,ld(6)-($s)+0.5),(ld(7)*($s)/ld(6)-ld(4))*ld(6)/hypot(ld(6),ld(7))+0.5),0,1)"
}

# render_arrow_png n: draw arrow number n (1-based) as a transparent PNG in $tmp. The alpha is
# computed per pixel by geq, mirroring arrowgeom.coverage: u/v are the position along/across
# the arrow axis, the shaft and each head are anti-aliased shapes, the arrow is their union.
# ffmpeg expressions only have 10 st/ld slots: 0 len, 1 ux, 2 uy, 3 u, 4 v, 5 k, 6 Lh, 7 Hw.
render_arrow_png() {
  local n="$1" ln x1 y1 x2 y2 t color ss es ox oy
  IFS=: read -r ln x1 y1 x2 y2 t color ss es ox oy <<< "${arrows[$((n-1))]}"
  local pad=$(( HEAD_HALF_K * t + HEAD_HALF_ADD + 2 ))
  local dx=$(( x2 - x1 )) dy=$(( y2 - y1 ))
  local ax=$(( x1 - ox )) ay=$(( y1 - oy ))  # start point in the image
  local w=$(( (x1 > x2 ? x1 : x2) - ox + pad + 1 )) h=$(( (y1 > y2 ? y1 : y2) - oy + pad + 1 ))
  local lh0=$(( HEAD_LEN_K * t + HEAD_LEN_ADD )) hw0=$(( HEAD_HALF_K * t + HEAD_HALF_ADD ))
  local heads=0 u0="0" u1="ld(0)"
  if [ "$ss" = arrow ]; then heads=$((heads+1)); u0="ld(6)-1"; fi
  if [ "$es" = arrow ]; then heads=$((heads+1)); u1="ld(0)-ld(6)+1"; fi
  local px="(X+0.5-$ax)" py="(Y+0.5-$ay)"
  local ex="st(0,hypot($dx,$dy));st(1,($dx)/ld(0));st(2,($dy)/ld(0))"
  ex+=";st(3,$px*ld(1)+$py*ld(2));st(4,abs($py*ld(1)-$px*ld(2)))"
  ex+=";st(5,min(1,ld(0)/($(( heads > 0 ? heads : 1 ))*$lh0)));st(6,$lh0*ld(5));st(7,$hw0*ld(5))"
  local cov="clip(min(min(ld(3)-($u0)+0.5,($u1)-ld(3)+0.5),$t/2-ld(4)+0.5),0,1)"
  local s
  if [ "$es" = arrow ]; then s="ld(0)-ld(3)"; cov="max($cov,$(head_cov "$s"))"; fi
  if [ "$ss" = arrow ]; then s="ld(3)"; cov="max($cov,$(head_cov "$s"))"; fi
  ex+=";$ARROW_ALPHA*$cov"
  ffmpeg -y -nostdin -loglevel error -f lavfi -i "color=c=0x$color:s=${w}x${h},format=rgba" \
    -frames:v 1 -vf "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='$ex'" "$tmp/arrow$n.png" \
    || { echo "$list:$ln: could not draw the arrow image" >&2; exit 1; }
}

inputs=()
for ((i = 1; i <= na; i++)); do
  render_arrow_png "$i"
  inputs+=(-loop 1 -i "$tmp/arrow$i.png")
done

ffmpeg -y -nostdin -hide_banner -stats -i "$in" "${inputs[@]+"${inputs[@]}"}" \
  -filter_complex "$graph" -map "[$cur]" -map 0:a? -c:a copy "$out"
