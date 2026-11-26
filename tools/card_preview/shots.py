"""Render the card against the mock backend and save screenshots (dev tool)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/card_shots")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])

        async def shot(name: str, *, role: str = "owner", view: str = "", width: int = 400, height: int = 860, steps=None):
            page = await browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            await page.goto(f"file://{HERE}/mock.html?role={role}&view={view}")
            await page.wait_for_timeout(300)
            for js in steps or []:
                await page.evaluate(js)
                await page.wait_for_timeout(150)
            await page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            if errors:
                print(name, "ERRORS:", errors)
            await page.close()

        click = lambda sel: f"document.getElementById('card').shadowRoot.querySelector(`{sel}`).click()"  # noqa: E731
        await shot("01_owner_door")
        await shot("02_owner_people", steps=[click('[data-tab="people"]')])
        await shot("03_owner_codes", steps=[click('[data-tab="codes"]')])
        await shot("04_owner_timeline", steps=[click('[data-tab="timeline"]')])
        await shot("05_wizard_step2", steps=[
            click('[data-tab="people"]'), click('[data-action="add-person"]'),
            "const c=document.getElementById('card'); c.s.form.name='Ahmed'; c.s.form.mode='link'; c._render()",
            click('[data-action="wiz-next"]'),
        ])
        await shot("06_person_detail", steps=[click('[data-tab="people"]'), click('[data-action="person"][data-id="p3"]')])
        await shot("07_enrol_progress", steps=[
            click('[data-tab="people"]'), click('[data-action="person"][data-id="p2"]'),
            click('[data-action="enrol"][data-method="fingerprint"]'),
            "window.pushers[0]({topic:'enrol', data:{session:{person_id:'p2', method:'fingerprint', state:'enrolling', presses_needed:4, presses_done:2}}})",
        ])
        await shot("08_enrol_done", steps=[
            click('[data-tab="people"]'), click('[data-action="person"][data-id="p2"]'),
            click('[data-action="enrol"][data-method="fingerprint"]'),
            "window.pushers[0]({topic:'enrol', data:{session:{person_id:'p2', method:'fingerprint', state:'done', presses_needed:4, presses_done:4, lock_ref:16}}})",
        ])
        await shot("09_new_code_weekly", steps=[
            click('[data-tab="codes"]'), click('[data-action="new-code"]'), click('[data-kind="weekly"]'),
            click('[data-day="0"]'), click('[data-day="3"]'),
        ])
        await shot("10_code_done", steps=[
            click('[data-tab="codes"]'), click('[data-action="new-code"]'),
            "const c=document.getElementById('card'); c.s.form.name='Electrician'; c._render()",
            click('[data-action="code-create"]'),
        ])
        await shot("11_family", role="family")
        await shot("12_tablet", role="tablet", width=800, height=900)
        await shot("13_arabic_people", steps=[click('[data-action="lang"]'), click('[data-tab="people"]')])
        await shot("14_arabic_door", steps=[click('[data-action="lang"]')])
        await browser.close()


asyncio.run(main())
