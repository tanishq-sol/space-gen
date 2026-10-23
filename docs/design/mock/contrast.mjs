// Computes WCAG contrast for every text/background pair the mock uses.
// Run: node docs/design/mock/contrast.mjs
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const over = (fg, a, bg) => fg.map((c, i) => c * a + bg[i] * (1 - a));

const T = {
  vellum: hex('#F5F7FA'), paper: hex('#FFFFFF'), ink: hex('#0B1F3A'), navy: hex('#1B3A6B'),
  slate: hex('#4D6080'), muted: hex('#5E6F8A'), error: hex('#B42318'), white: hex('#FFFFFF'),
};
const dark = hex('#202020'), black = hex('#000000'), light = hex('#FFFFFF');
const GLASS_A = Number(process.env.GLASS_A || 0.88);
const glassDark = over(T.white, GLASS_A, dark);
const glassBlack = over(T.white, GLASS_A, black);
const glassLight = over(T.white, GLASS_A, light);
// selected row: navy at 10% over the glass layer
const selOnGlass = over(T.navy, 0.1, glassDark);
// chip behind clear-glass icons: black 35% dim over scan, plus white 30% glass
const clearChip = over(T.white, 0.3, over(black, 0.35, hex('#BFB8A8')));

const rows = [
  ['ink on paper', T.ink, T.paper, 4.5],
  ['ink on vellum', T.ink, T.vellum, 4.5],
  ['slate on vellum', T.slate, T.vellum, 4.5],
  ['muted on vellum', T.muted, T.vellum, 4.5],
  ['muted on paper', T.muted, T.paper, 4.5],
  ['white on navy (primary button)', T.white, T.navy, 4.5],
  ['navy on paper (links, selected label)', T.navy, T.paper, 4.5],
  ['error on paper', T.error, T.paper, 4.5],
  [`ink on glass ${GLASS_A * 100}% over #202020`, T.ink, glassDark, 4.5],
  [`slate on glass ${GLASS_A * 100}% over #202020 (worst case)`, T.slate, glassDark, 4.5],
  [`muted on glass ${GLASS_A * 100}% over #202020 (forbidden pair: muted is opaque-only)`, T.muted, glassDark, 0],
  [`navy on glass ${GLASS_A * 100}% over #202020`, T.navy, glassDark, 4.5],
  [`slate on glass ${GLASS_A * 100}% over #000000`, T.slate, glassBlack, 4.5],
  [`slate on glass ${GLASS_A * 100}% over #FFFFFF`, T.slate, glassLight, 4.5],
  ['ink on selected row (navy 10% over dark-worst glass)', T.ink, selOnGlass, 4.5],
  ['navy on selected row (navy 10% over dark-worst glass)', T.navy, selOnGlass, 4.5],
  ['ink on clear-glass chip over bright scan (icon, 3:1)', T.ink, clearChip, 3],
  ['hairline vs paper (decorative, 3:1 not required)', hex('#DDE3EC'), T.paper, 0],
];
let fail = 0;
for (const [name, fg, bg, min] of rows) {
  const r = ratio(fg, bg);
  const ok = r >= min;
  if (!ok) fail++;
  console.log(`${r.toFixed(2).padStart(6)}:1  ${ok ? 'pass' : 'FAIL'} (min ${min || 'n/a'})  ${name}`);
}
console.log(fail ? `${fail} failing` : 'all pass');
