# ADR-0022 — Deterministic ICS adapter with human review (F4.1)

Date: 2026-09-23 · Status: Accepted

## Decision
`infrastructure/ics.py`: export with stable UIDs (stable ids), explicit
DTSTAMP, CRLF + 75-octet folding, one RRULE VEVENT per class series;
import bounded (2 MiB, 5000 events, 8 KiB lines), UTC -> peninsular time
without tzdata (Gestion rule). Import is preview -> apply; the subject is
only suggested when similarity >= 0.6, else `needs_review`; duplicates
(title+date) are skipped.
