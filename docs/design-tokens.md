# Kýrauga Design Tokens

Kýrauga is currently using Tailwind CSS v3.4.19, so the brand tokens live in `theme.extend` in `tailwind.config.js`. If the project upgrades to Tailwind CSS v4, these values should move to CSS-first `@theme` variables.

## Colors

| Token | Value | Use |
| --- | --- | --- |
| `brand` | `#66f1d2` | Primary Kýrauga identity color. Keep central and use with restraint. |
| `brand-strong` | `#43dfbe` | Hover states, active states, and stronger brand emphasis. |
| `brand-soft` | `#c8fbef` | Badges, subtle highlights, and selection-adjacent surfaces. |
| `secondary` | `#2f5fd0` | Links and secondary actions. |
| `secondary-strong` | `#1f3f7a` | Link hovers and high-contrast secondary text. |
| `secondary-soft` | `#dbe5ff` | Secondary action backgrounds and quiet callouts. |
| `accent` | `#d97b2d` | Warm editorial accents. |
| `accent-soft` | `#e6a34a` | Softer warm highlights. |
| `tertiary` | `#c44536` | Tertiary emphasis and shared danger color. |
| `bg` | `#eef3f1` | Default page background. |
| `bg-soft` | `#f6faf8` | Softer page bands and quiet sections. |
| `surface` | `#ffffff` | Cards and raised surfaces. |
| `surface-muted` | `#e5eeeb` | Muted panels and subdued content areas. |
| `text` | `#1f2933` | Primary readable text. |
| `text-muted` | `#61717b` | Supporting copy and metadata. |
| `text-soft` | `#7b8b94` | Low-emphasis text. |
| `border` | `#dbe5e1` | Default dividers and surface borders. |
| `border-strong` | `#b8c7c1` | Stronger borders and interactive outlines. |
| `success` | `#2d8f6f` | Success messages and positive status. |
| `warning` | `#b7791f` | Warning messages and caution status. |
| `danger` | `#c44536` | Error messages and destructive status. |

## Typography

| Token | Value | Use |
| --- | --- | --- |
| `font-display` | `"AXIS-ExtraBold", "Arial Black", sans-serif` | Brand titles, hero display text, and major editorial moments. |
| `font-body` | `Inter, ui-sans-serif, system-ui, sans-serif` | Body copy, navigation, UI labels, and form text. |

Use AXIS sparingly so it keeps its brand weight. Body text should remain in `font-body` for legibility.

## Radius

| Token | Value | Use |
| --- | --- | --- |
| `rounded-sm` | `0.375rem` | Small controls and compact labels. |
| `rounded-md` | `0.75rem` | Buttons and common interactive elements. |
| `rounded-lg` | `1.25rem` | Surfaces and cards. |
| `rounded-xl` | `1.75rem` | Larger editorial surfaces. |
| `rounded-2xl` | `2.5rem` | Large feature panels. |

## Shadows

| Token | Value | Use |
| --- | --- | --- |
| `shadow-soft` | `0 8px 30px rgba(31, 41, 51, 0.08)` | Quiet elevation for surfaces. |
| `shadow-card` | `0 12px 40px rgba(31, 41, 51, 0.12)` | Stronger card or hover elevation. |

## Spacing

| Token | Value | Use |
| --- | --- | --- |
| `page` | `1.5rem` | Standard page edge padding. |
| `section` | `4rem` | Default vertical section rhythm. |
| `section-lg` | `6rem` | Larger editorial section spacing. |

## Component Classes

| Class | Intended use |
| --- | --- |
| `.ky-page` | Default page shell color, background, and text styling. |
| `.ky-surface` | Raised white content surface. |
| `.ky-surface-muted` | Raised muted content surface. |
| `.ky-title` | Brand display title treatment. |
| `.ky-kicker` | Small uppercase metadata or section label. |
| `.ky-link` | Branded inline link. |
| `.ky-button-primary` | Primary action with brand color. |
| `.ky-button-secondary` | Secondary action with outlined surface treatment. |
| `.ky-badge` | Small brand label or status chip. |
| `.ky-border` | Standard tokenized border. |
