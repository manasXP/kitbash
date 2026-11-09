---
modified: 2026-04-02
---
# Rillet firmware updates

## Signing

The bootloader rejects any image without a valid signature, with no exceptions.

## Image slots

Rev A kept two image slots; rev B replaced that with three, so a failed update can
always fall back. The updater writes to the oldest of the three slots.

## Duration

An update typically takes 40 s. The worst case, on a weak connection, is 3 minutes.

## Recovery

Over USB, the bootloader installs any image it is given, signed or not, so a technician
can recover a unit that no longer boots.

## Release notes

Release notes are published on the first Monday of each month.
