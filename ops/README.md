# ops/

Deployed to the mac-mini (`solberg.club`), not run from this repo. Kept here so
the dead-man's-switch is reviewable, diffable, and not one disk failure from
being lost.

| File | Deployed to |
|------|-------------|
| `icelandic-data-dms.sh` | `~/clawd/bin/icelandic-data-dms.sh` |
| `com.jokull.icelandic-data-dms.plist` | `~/Library/LaunchAgents/` |

The switch answers "is anyone still watching?" — it polls the age of the last
commit on the `health-history` branch and alerts via Telegram when observations
stop. It says nothing about whether the data sources are healthy; the workflow
already answers that, with detail.

See the "blind spot" section in `AGENTS.md` for the reasoning and the invariants
worth preserving.

## Redeploy

```bash
scp ops/icelandic-data-dms.sh solberg.club:~/clawd/bin/
scp ops/com.jokull.icelandic-data-dms.plist solberg.club:~/Library/LaunchAgents/
ssh solberg.club 'chmod +x ~/clawd/bin/icelandic-data-dms.sh && \
  launchctl unload ~/Library/LaunchAgents/com.jokull.icelandic-data-dms.plist 2>/dev/null; \
  launchctl load ~/Library/LaunchAgents/com.jokull.icelandic-data-dms.plist'
```

## Exercise it

An untested dead-man's-switch is decoration. Both thresholds are env-overridable:

```bash
ssh solberg.club 'MAX_AGE_HOURS=0 ~/clawd/bin/icelandic-data-dms.sh'   # forces a real Telegram alert
ssh solberg.club 'rm -f ~/clawd/state/icelandic-data-dms.last-alert'   # reset the cooldown
ssh solberg.club 'tail ~/clawd/logs/icelandic-data-dms.log'
```

`NODE_BIN` and `OPENCLAW_JS` are pinned to match `ai.openclaw.gateway.plist`.
If openclaw is upgraded and node moves, update both — the script fails loudly
and refuses to stamp its cooldown rather than going quietly deaf.

## Upgrading openclaw

**Now on 2026.7.1 (2d2ddc4), node v24.15.0.** Upgraded 2026-07-17 from 2026.6.1.
It took three attempts; here is what actually bites, in order.

**1. Node version is the real gate.** 2026.7.1 needs node `>=22.22.3 <23`,
`>=24.15.0 <25`, or `>=25.9.0`. `fnm install v24.15.0` is not enough —
`fnm default v24.15.0 && fnm use v24.15.0`, and check `node --version` before
starting. The build clears `tsdown` (the slow 100s part) and then dies in
`write-cli-startup-metadata`, because that step *executes the CLI it just built*
and the new CLI refuses the old node. A failure there means node, not a bad build.

**2. Repoint the pins BEFORE updating**, or the gateway will not restart:

```bash
sed -i '' 's|v24\.12\.0|v24.15.0|g' ~/Library/LaunchAgents/ai.openclaw.gateway.plist
sed -i '' 's|v24\.12\.0|v24.15.0|g' ~/clawd/bin/icelandic-data-dms.sh
```

The updater does **not** rewrite the plist's hardcoded node path. Left at 24.12.0,
the gateway silently fails to come back and the DMS goes deaf.

**3. A failed build leaves the box half-broken, and `doctor` cannot help.**
The auto-rollback restores tracked source, but `dist/` and `node_modules` are
gitignored, so half-built artifacts survive. You get old source behind a new
launcher, and every command — including `openclaw doctor` — is refused by the new
engine gate. The repair tool sits behind the breakage. Symptom on the second
attempt: `Cannot find module '@openclaw/ai/internal/openai'`.

Recovery, verified twice — rebuild the artifacts from whatever source is checked out:

```bash
cd ~/openclaw
export PATH=~/.local/share/fnm/node-versions/v24.15.0/installation/bin:$PATH
corepack pnpm install --frozen-lockfile
node scripts/build-all.mjs            # ~110s
```

**4. Stale migration lock.** After a successful update the gateway may not come
back: `startup migrations are already running for this state directory`. A
crashed startup holds the lock, and launchd's KeepAlive respawns into it every
few seconds — a livelock that never clears itself. Break it:

```bash
launchctl bootout gui/501/ai.openclaw.gateway      # stop the thrash
# wait for the lock's stated expiry (it prints a UTC timestamp)
launchctl bootstrap gui/501 ~/Library/LaunchAgents/ai.openclaw.gateway.plist
```

## After any upgrade, verify in this order

```bash
openclaw --version                       # --version short-circuits; not proof
openclaw cron list                       # 5 jobs, 4 explicit telegram routes
lsof -nP -iTCP:18789 -sTCP:LISTEN        # gateway actually listening
MAX_AGE_HOURS=0 ~/clawd/bin/icelandic-data-dms.sh   # switch still audible
```

A gateway you have not restarted is unproven, and `openclaw --version` succeeding
proves nothing — it short-circuits before the engine gate. Use a real command.
