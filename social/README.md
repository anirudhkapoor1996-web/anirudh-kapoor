# Instagram posting — `social/`

This folder is the queue for the Designs Instagram account
(**@anirudh_kapoor_designs**). The `Instagram Publish` GitHub Action watches it.

## How to post a project

1. Create a folder named for the project ref, e.g. `social/A-02/`.
2. Drop in the rendered **1080 × 1350** slides (`slide-1.jpg`, `slide-2.jpg`, …)
   — these are the designed IG slides, *not* the website plate images.
3. Add a `post.json` (see template in `social/_TEMPLATE/`) with the caption and
   slide list, and set `"ready": true`.
4. Upload the folder to the repo. The Action publishes the carousel and writes a
   `.posted` marker so it never double-posts. You can also trigger it manually
   from the repo's **Actions → Instagram Publish → Run workflow**.

## `post.json`

```json
{
  "ref": "A-02",
  "type": "carousel",
  "ready": true,
  "caption": "House of Ming — a restoration in restraint.\n\n#interiordesign #hospitality",
  "media": ["slide-1.jpg", "slide-2.jpg", "slide-3.jpg"]
}
```

- `type`: `"carousel"` (2–10 slides), `"image"` (single), or `"reel"` (one `.mp4`).
- `ready`: must be `true` to publish. Leave `false` to stage without posting.
- `media`: filenames inside this project folder, in order.
- `cover` *(reels only, optional)*: a frame filename to use as the cover.

## Requirements

- Slides must be reachable publicly at
  `https://anirudh-kapoor.com/social/<ref>/<file>` over HTTPS — i.e. the site
  must be live with HTTPS enforced (Instagram fetches the images by URL).
- Repo secrets `IG_PAGE_TOKEN` and `IG_USER_ID` must be set (Settings → Secrets
  and variables → Actions).

Folders beginning with `_` (like `_TEMPLATE`) are ignored by the publisher.
