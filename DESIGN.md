---
name: AcademicCore
description: Calm Apple-workbench desktop UI for deterministic engineering study.
colors:
  accent-blue: "#007AFF"
  accent-text: "#0066CC"
  accent-soft: "#E5F0FF"
  ink: "#1D1D1F"
  secondary: "#6E6E73"
  tertiary: "#AEAEB2"
  sidebar: "#F5F5F7"
  ground: "#F2F2F6"
  card: "#FFFFFF"
  hairline: "#E2E2E8"
  field: "#FFFFFF"
  success-bg: "#E3F5E9"
  success-ink: "#187038"
  warning-bg: "#FFF2D2"
  warning-ink: "#8A5A00"
  error-bg: "#FDE7E7"
  error-ink: "#B3261E"
  info-bg: "#E5F0FF"
  info-ink: "#0B5CAD"
  idle-bg: "#E9E9EE"
  idle-ink: "#6E6E73"
typography:
  display:
    fontFamily: '"Segoe UI", "SF Pro Text", -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "15pt"
    fontWeight: 700
  headline:
    fontFamily: '"Segoe UI", "SF Pro Text", -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "11pt"
    fontWeight: 600
  title:
    fontFamily: '"Segoe UI", "SF Pro Text", -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "10pt"
    fontWeight: 600
  body:
    fontFamily: '"Segoe UI", "SF Pro Text", -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "9pt"
    fontWeight: 400
  label:
    fontFamily: '"Segoe UI", "SF Pro Text", -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "8.5pt"
    fontWeight: 400
rounded:
  sm: "7px"
  md: "8px"
  lg: "12px"
spacing:
  sm: "6px"
  md: "12px"
  lg: "16px"
  xl: "28px"
components:
  button-primary:
    backgroundColor: "{colors.accent-blue}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  button-default:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  button-subtle:
    backgroundColor: "transparent"
    textColor: "{colors.accent-text}"
    rounded: "{rounded.sm}"
    padding: "6px 14px"
  card-home:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "14px 16px"
  input-field:
    backgroundColor: "{colors.field}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "5px 8px"
  status-pill:
    backgroundColor: "{colors.idle-bg}"
    textColor: "{colors.idle-ink}"
    rounded: "8px"
    padding: "3px 10px"
---

# Design System: AcademicCore

## Overview

**Creative North Star: "The Calm Instrument"**

AcademicCore is a precision instrument — every solve proves its conservation
laws, every grade reproduces exactly — so its surface behaves like good lab
equipment: quiet, exact, and instantly readable. The visual world is an Apple
workbench translated to Qt on Windows: a tinted sidebar for navigation,
grouped white cards on a quiet gray ground, one blue accent spent only on
selection, primary action, and live state. Nothing glows, nothing parades;
the product's determinism is the personality, and the interface disappears
into the task.

Density is welcome where the task needs it (transition tables, netlists,
capture lists), but chrome never competes with content: color lives inside
figures and status pills, never in decoration. Dark mode is the same
instrument after hours — graphite grounds, lifted cards, a brighter blue —
chosen by the room, not by the category.

**Key Characteristics:**
- Restrained: neutrals plus one accent, spent sparingly.
- Tonal depth: layers separated by tone and hairlines, never shadows.
- Native discipline: system sans, standard pulleys (tabs, trees, tables), no invented affordances.
- Live proof: home cards and results always show real facade state and digests.

## Colors

Quiet Apple neutrals with a single blue accent; semantic hues quarantined to state.

### Primary
- **Instrument Blue** (#007AFF): selection, primary actions, focus rings, live accents. Dark mode: Clear Night Blue (#0A84FF).
- **Spoken Blue** (#0066CC): accent text on light grounds (holds 5.57:1 on white). Dark mode: Signal Ice (#7AB8FF, 8.2:1 on graphite).
- **Blue Wash** (#E5F0FF): selected rows, tabs, and soft fills. Dark mode: translucent blue (rgba(10,132,255,0.18)).

### Neutral
- **Ink** (#1D1D1F): primary text (16.8:1 on white). Dark mode: Paper White (#F5F5F7).
- **Pencil Gray** (#6E6E73): secondary text, captions (5.07:1 on white, 4.54:1 on ground). Dark mode: Moon Gray (#AEAEB2).
- **Faint Gray** (#AEAEB2): tertiary marks, scrollbars, disabled hints.
- **Sidebar Mist** (#F5F5F7): sidebar, menus, status bar. Dark mode: Graphite Sidebar (#232328).
- **Lab Ground** (#F2F2F6): content background. Dark mode: Night Bench (#1C1C1F).
- **Bench Card** (#FFFFFF): cards, fields, tables. Dark mode: Lifted Slate (#2C2C31).
- **Hairline** (#E2E2E8): 1px borders and dividers. Dark mode: Graphite Line (#3C3C43).

### Named Rules (state quarantine)
- **Verdict Green** bg (#E3F5E9) / ink (#187038, 5.42:1): SUCCESS only.
- **Caution Amber** bg (#FFF2D2) / ink (#8A5A00, 5.33:1): WARNING only.
- **Fault Red** bg (#FDE7E7) / ink (#B3261E, 5.53:1): ERROR only.
- **Signal Blue** bg (#E5F0FF) / ink (#0B5CAD, 5.79:1): RUNNING only.
- **Idle Stone** bg (#E9E9EE) / ink (#6E6E73): IDLE only.
- **The Quarantine Rule.** Semantic color appears inside status pills, validation, and figures — never as page decoration, never as a border stripe.
- **The One Voice Rule.** The accent fills at most one primary action per row and the current selection; everywhere else it speaks as text or wash.

## Typography

**Display Font:** System sans ("Segoe UI" on Windows, SF Pro where present, Helvetica Neue, Arial).
**Body Font:** Same stack — one family carries everything.
**Label/Mono Font:** System sans for labels; monospace ("Cascadia Mono", SF Mono, Consolas) quarantined to netlists, digests, and code editors.

**Character:** Neutral, legible, unshowy. Headings differ by size and weight, never by family; data reads in tabular figures, prose at a calm 9pt.

### Hierarchy
- **Display** (bold 700, 15pt): home greeting only ("AcademicCore — Dashboard").
- **Headline** (semibold 600, 11pt): card titles.
- **Title** (semibold 600, 10pt): section headers inside panels.
- **Body** (regular 400, 9pt): controls, lists, tables, prose.
- **Label** (regular 400, 8.5pt, secondary ink): captions, hints, card status lines, provenance footers. Status pills reuse this size at semibold on tinted grounds.

### Named Rules
- **The One Family Rule.** No display face, no pairing; weight and size carry hierarchy.
- **The Mono Quarantine Rule.** Monospace is for machine text (netlists, digests, code), never for a "technical" costume on prose.

## Layout

Sidebar workbench: a 300px tinted sidebar (academic tree + Add/Delete) beside
a fluid content column; a slim action row sits above the tab strip; a status
bar carries version, offline state, and db path; the session log docks right.
The home is a 2-column grouped-card grid (28px page margins, 16px section
gaps, 12px card gaps, 14–16px card padding). Panels keep their task layouts
and share one vocabulary: control row on top, work surface in the middle,
output card below, status pill at the row's end.

### Named Rules
- **The Sidebar Owns Going, Panels Own Doing.** Navigation lives in the sidebar, home cards, and tabs; panels never rebuild navigation.
- **The One Action Rule.** Each card and each control row has exactly one primary action; the rest are quiet.

## Elevation & Depth

No shadows anywhere — Qt's styling engine does not do soft blurred shadows
well, so the system does not pretend. Depth is tonal: sidebar, ground, card,
and field are four distinct tones separated by 1px hairlines. Selected things
are marked with the blue wash plus semibold text, never with lift.

### Named Rules
- **The Flat-By-Construction Rule.** If depth cannot be a soft offset blur, it must be tone. No halo, no hard offset block, no gradient bevel.

## Shapes

Gently rounded rectangles throughout: controls and fields at 7px, output
cards and tables at 8px, home cards at 12px, status pills at 8px, tab
selections at 7px. Borders are always 1px hairlines; focus is a 1px accent
ring (border recolor, no glow). Scrollbars are thin (10px) with 4px thumb
radii and no arrow buttons.

## Components

### Buttons
- **Shape:** rounded rectangle (7px radius), 6px vertical / 14px horizontal padding.
- **Primary:** Instrument Blue fill, white semibold text; hover keeps fill and lightens the border; disabled falls to Idle Stone with tertiary text.
- **Default:** card fill, 1px hairline border, ink text; hover recolors the border to accent; pressed drops to blue wash.
- **Subtle:** borderless, Spoken Blue semibold text (contrast-safe); hover shows the blue wash. Used for per-card Open actions.
- **Dialogs:** minimum 400px wide; the OK button is primary and default.

### Status pills
- **Style:** 8px pill, 3px/10px padding, semibold 8.5pt label on the state's tinted ground (see Colors). Every long-running panel ends its control row with one; it repolishes on every state change (IDLE → RUNNING → SUCCESS / WARNING / ERROR).

### Cards / Containers
- **Corner Style:** softly rounded (12px home cards).
- **Background:** Bench Card on Lab Ground (Lifted Slate on Night Bench in dark).
- **Shadow Strategy:** none — tonal layering per Elevation & Depth.
- **Border:** 1px hairline.
- **Internal Padding:** 14px vertical, 16px horizontal; 6px between title, description, live status, and action row.

### Inputs / Fields
- **Style:** field fill, 1px hairline, 7px radius, 5–8px padding; combos and spin/date edits match.
- **Focus:** border recolors to accent; nothing else moves.
- **Error / Disabled:** disabled text falls to tertiary on ground fill; errors are named by the single D2 converter dialog, never by red chrome alone.

### Navigation
- **Tabs:** clean text tabs, 7px/14px padding; hover shows idle wash; selected tab is semibold ink on blue wash. Thirteen tabs scroll natively with arrow buttons — a pinned product fact, handled by the platform affordance.
- **Go menu:** grouped shell (Home / Learn / Practice / Engineering / Settings + Engineering modules index) mapping onto the same tabs; adds orientation without touching tab structure.
- **Search:** Ctrl+K palette over UnifiedSearchService; subject hits select the sidebar node.
- **Sidebar tree:** transparent rows, 6–8px padding, 7px selection radius; selected item is semibold ink on blue wash.
- **Menus:** a View → Appearance menu (Follow system / Light / Dark) persists to platform settings and re-applies the world live; mirrored in the Settings tab.
- **Lab workspaces:** Virtual Lab and Simulation group the same pinned controls into Experiment / Inputs / Execution / Results sections; no widget renamed, no text changed.
- **Motion:** dialog appearance is a 150 ms OutCubic opacity fade (no bounce); scale was deliberately avoided — Qt geometry animation on laid-out dialogs causes relayout jitter.

### Tables and outputs
- Headers are semibold secondary text with a hairline underline, no filled header bars; gridlines are hairlines; selection is blue wash with ink text. Read-only outputs sit in 8px cards. The waveform draws lanes in ink, axes and ticks dimmed, trigger as a dashed accent line with text label — color is never the only cue (H/L labels, lane names, trigger text persist).

## Do's and Don'ts

### Do:
- **Do** spend the accent only on selection, one primary action, focus, and live state.
- **Do** put live facade state and digests where the user looks first (home summaries, run headers, status pills).
- **Do** keep the four tones distinct in both modes (sidebar / ground / card / field).
- **Do** name errors with problem + recovery (single converter), and mirror state in the pill.
- **Do** verify accent text contrast per mode (≥4.5:1; current pairs: 5.57 light, 8.2 dark).

### Don't:
- **Don't** add kickers or eyebrows above headings; the heading carries its own weight.
- **Don't** decorate with gradients, glass, glow, emoji icons, or border stripes.
- **Don't** use mono or color as costume — mono is for machine text, color is for state and figures.
- **Don't** choreograph entrances; motion is 150–250ms state feedback only.
- **Don't** rename tabs, widgets, or move logic into the UI layer to serve the design (test-pinned contracts and the facade boundary are load-bearing).
