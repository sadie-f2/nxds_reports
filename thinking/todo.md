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
- [ ] Cut production Nexudus API key (NEXUDUS_BOOKING_TOKEN) and test
