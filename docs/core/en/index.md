---
id: index
section: root
title_key: docs.index.title
targets:
  - dsm
  - web
order: 0
---

# ImgData

ImgData helps you analyze, validate, and maintain photo metadata and face assignments in Synology Photos. Compute-intensive image-processing tasks can optionally be offloaded to an external worker.

## Status

Describes the ImgData Status view and the package, database, and component information shown there. Runtime state for individual functions is documented in the corresponding help sections.

## Face Matching

Searches and compares faces between Synology Photos and image files, finds missing face markings, and supports assigning unknown faces to persons.

## Checks

Checks images and face metadata for issues such as invalid dimensions, duplicate face markings, deviating face positions, name conflicts, and implausible person assignments.

## Cleanup

Cleans up and normalizes existing data, including names, face frames, and reference data used for face recognition.

## Face recognition and person profiles

Builds and maintains reference profiles from existing person faces and uses them for recognition, scoring, and validation of face assignments.

## Configuration

Defines basic settings for metadata, file and sidecar processing, checks, face recognition, and other package functions.

## External Worker

Configures optional offloading of compute-intensive image and face processing to an external Windows or Linux system and manages registered workers.

## External libraries

Shows and manages external components used by individual functions, including ExifTool, InsightFace-compatible models, the native face processor, and libvips.

## Database lists

Shows and manages persistent mapping and ignore lists used by validation, cleanup, and assignment functions.

## Preview and review

Describes the common handling of image and face previews and how to review, select, save, skip, and continue through findings.

## Troubleshooting

Provides guidance for diagnosing common problems with files, metadata, Synology Photos, face recognition, external components, and workers.
