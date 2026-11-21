# Share images

`card.html` draws the 1200 x 630 image shown when the site is linked in a chat or a social post.
`src/og-ka.png` and `src/og-en.png` are rendered from it with Chrome (from this `website/` folder):

```bash
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"   # or google-chrome on Linux
for l in ka en; do
  "$CH" --headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=1200,630 \
    --virtual-time-budget=3000 --allow-file-access-from-files \
    --screenshot="$PWD/src/og-$l.png" "file://$PWD/og/card.html?lang=$l"
done
```
