# Catalog App Review

What we check before an app goes in the Cloud in a Bottle catalog. A review is a
straight **include or exclude** decision: work through the points below, fix what
you can, and if an app still falls short of the bar, leave it out of the catalog
rather than shipping it. An app is in the catalog only because it passed this
review — there is no numeric rating.

## What a review checks

1. **Sign-in works as described.** Try it yourself:
   - The **owner** is signed in automatically. Barring an unusual circumstance,
     the owner should never have to make an account or enter a password to use an
     OpenHost app — no login screen, no hunting for a password.
   - **Everyone else** is handled right: sent to the login page for a private
     app, or shown shared/public content without being signed in as the owner.
   - **No onboarding flow.** Wherever the platform allows it, an app should have
     no signup or first-boot setup — we handle auth for you, so there's no
     account to create. Configuration should be pre-determined and baked into the
     app or wrapper repo based on what makes sense for a bottle user, rather than
     asking a bunch of questions on first boot. Ideally apps come up and are
     immediately usable.

2. **The app works — all of it.** It does the thing it's for — not just "the
   container starts." Add the feed, record the video, play the game. If the main
   feature is broken, it's not ready, however clean the rest is. No part of the
   app should be broken by the integration into Cloud in a Bottle. Things like
   share-link generation should be tested and adapted to work properly within the
   platform. If something genuinely can't work, make that
   clear in-product rather than leaving it non-obviously broken.

3. **Data survives a restart.** Anything the user creates is kept when the app is
   redeployed — not lost with the container.

4. **The README explains the app.** A reader should learn what it is, who it's
   for, and how to start; a wrapper should link the project it packages. A small
   wrapper's README should focus on Cloud in a Bottle; a larger project should
   at least mention and link it (a separate Cloud in a Bottle page is fine).

5. **Our original code is MIT-licensed.** Original applications and Cloud in a
   Bottle packaging that we maintain should offer the MIT License, with the full
   license text and a clear scope. Upstream applications, copied or adapted
   third-party code, and assets retain their own licenses and copyright notices.
   Record the application's license in the catalog entry's `license` field and
   the packaging's license in `packaging_license`, checking each against its
   license text where applicable.

6. **Resource limits are accurate.** Memory and CPU limits should match what the
   app really uses — measured, not guessed. Some apps need more memory to build
   than to run; when so, give the build a higher limit of its own.

7. **The app is reasonably secure.** No obvious security holes — for example, it
   must not leak passwords, keys, or tokens into its logs. It also shouldn't
   request any permissions or privileges that aren't necessary for the purpose of
   the app.

## Include or exclude

A review ends in one of two outcomes: the app goes in the catalog, or it
doesn't. Judge how well the app fits the platform — mainly
single sign-on and how it treats the owner and guests — not how good the
underlying app is. A great project with a clunky fit doesn't belong here; a
simple app that fits perfectly does.

The bar for inclusion:

- **Owner sign-in should be automatic.** An app where the owner has to log in
  through the app's own form each time is a poor fit — fix the integration or
  leave it out.
- **Guests and shared links should behave.** Non-owners are bounced to the zone
  login, or, for apps with public sharing, served the shared content without
  being signed in as the owner.
- **No usable secrets on disk.** If the app leaves a password or long-lived token
  where another app could read it, that's a hard blocker — fix it before the app
  ships.

**Don't penalize what doesn't apply.** A public, account-free service has no
guests to sign in and no secrets to leak — it can still be a perfect fit.
Account systems that are external to the app or used for encryption are fine.
