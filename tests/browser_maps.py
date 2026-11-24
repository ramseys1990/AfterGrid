"""Disposable browser acceptance against the local CI server.

Block every off-server browser request. This is not a physical WAN outage or
server-side network isolation test. Uses the pinned raster fixture and OSM PBF.
"""
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

BASE="http://127.0.0.1:8080"

def browser_maps():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--use-angle=swiftshader","--enable-unsafe-swiftshader","--disable-background-networking"])
        context=browser.new_context(viewport={"width":1280,"height":900},service_workers="block")
        external=[]
        errors=[]
        range_responses=[]
        def intercept(route):
            url=urlsplit(route.request.url)
            if url.scheme in ("http","https") and (url.scheme,url.netloc)!=("http","127.0.0.1:8080"):
                external.append(route.request.url)
                route.abort()
            else:route.continue_()
        context.route("**/*",intercept)
        page=context.new_page()
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("response",lambda r:range_responses.append(r.status) if "/maps/archive.pmtiles" in r.url else None)
        try:
            page.goto(BASE)
            expect(page.locator("#dashboard")).to_be_visible(timeout=30000)
            page.locator("#auth").click()
            page.locator("#login-form [name=username]").fill("admin")
            page.locator("#login-form [name=password]").fill("a disposable test password")
            page.locator("#login-form button[type=submit], #login-form button:not([type])").first.click()
            expect(page.locator("#admin")).to_be_visible(timeout=30000)
            page.locator("#region-preset").select_option("sc")
            expect(page.locator("#map-estimate [name=west]")).to_have_value("-83.4000")
            expect(page.locator("#map-estimate [name=east]")).to_have_value("-78.4000")
            page.goto(BASE+"/maps")
            expect(page.locator("body")).to_have_attribute("data-map-ready","true",timeout=60000)
            expect(page.locator("#map canvas.maplibregl-canvas")).to_be_visible()
            assert 206 in range_responses,range_responses
            page.locator("#route-form [name=start]").fill("9.5209,47.1394")
            page.locator("#route-form [name=end]").fill("9.5238,47.1417")
            page.locator("#route-form [name=mode]").select_option("auto")
            page.locator("#route-form button").first.click()
            expect(page.locator("#route-message")).to_contain_text("Primary route:",timeout=45000)
            expect(page.locator("body")).to_have_attribute("data-route-ready","true",timeout=30000)
            page.locator("#route-details summary").click()
            expect(page.locator("#route-directions li").first).to_be_visible()
            page.locator("#place-panel summary").click()
            page.locator("#place-search [name=q]").fill("Vaduz")
            page.locator("#place-search button").click()
            expect(page.locator("#place-results>div").first).to_be_visible(timeout=20000)
            page.locator("#plans-panel summary").click()
            expect(page.locator("#plan-admin")).to_be_visible(timeout=20000)
            page.locator("#waypoint-form [name=name]").fill("CI meeting point")
            page.locator("#waypoint-form [name=coords]").fill("9.5209,47.1394")
            page.locator("#waypoint-form button").last.click()
            expect(page.locator("#waypoints-list")).to_contain_text("CI meeting point")
            page.locator("#save-route [name=name]").fill("CI route")
            page.locator("#save-route button").click()
            expect(page.locator("#routes-list")).to_contain_text("CI route")
            # Guest: fresh browser session, no administrator cookies.
            context.clear_cookies()
            page.reload()
            expect(page.locator("body")).to_have_attribute("data-map-ready","true",timeout=60000)
            page.locator("#plans-panel summary").click()
            expect(page.locator("#plan-admin")).to_be_hidden()
            expect(page.locator("#waypoints-list")).to_contain_text("CI meeting point")
            expect(page.locator("#routes-list")).to_contain_text("CI route")
            page.locator("#routes-list button",has_text="View").click()
            expect(page.locator("#route-message")).to_contain_text("Saved route snapshot: CI route")
            assert not external,external
            assert not errors,errors
            print("Browser acceptance passed: local raster map, region preset, route overlay, search, saved plans, guest read; no off-server browser requests.")
        finally:
            context.close()
            browser.close()
