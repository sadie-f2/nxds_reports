# Todo / pending actions

## Git housekeeping

- [ ] Merge `feature/linked-resource-grouping` into `main` once toolsched is
      confirmed stable, then switch the server back to tracking `main`.
      ```
      git checkout main
      git merge feature/linked-resource-grouping
      git push
      # on server:
      git checkout main
      git pull
      sudo systemctl restart a2-bookings.service
      ```

## Booking app

- [ ] Warm member list cache on app startup to eliminate sign-in lag
- [ ] View-only calendar mode (no login required, booking/cancel hidden)
- [ ] Cut a scoped Nexudus Bearer token for production (replace email/password in .env)
- [ ] Inline identity gate UX — already done in v0.2.3; monitor for feedback
- [ ] Consider relaxing fail2ban rules slightly to reduce false positives
      (currently findtime=30 maxretry=15 — one legit member banned so far)

## Server / infrastructure

- [ ] Install etckeeper on the wiki/booking server to put /etc under git
- [ ] Set up wiki_monitor.sh on a separate machine to log slow responses
      to /var/www/html/wikilog.txt
- [ ] Replace personal Nexudus credentials with a dedicated service account.
      Nexudus API key situation: no clean option for private internal apps.
      - Bearer tokens are short-lived and require refresh
      - App Key/Secret requires registering through the marketplace process
        even for private apps — not worth the overhead for one internal tool
      Best practice given constraints:
      1. Create a dedicated Nexudus staff account e.g. bookingapp@artisansasylum.com
         with minimum admin role needed (Spaces + Billing read/write)
      2. Put those credentials in .env as NEXUDUS_EMAIL / NEXUDUS_PASSWORD
      3. Leave NEXUDUS_BOOKING_TOKEN blank
      This decouples the service from any personal account and makes
      revocation easy (just disable the service account).
