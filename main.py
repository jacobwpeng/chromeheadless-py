#!/usr/bin/env python
import asyncio
import base64
from pprint import pprint

import re
import sys
import pdir
import random
import logging
import itertools
import datetime
import pyppeteer
from pyppeteer.page import Page
from pyppeteer.errors import PyppeteerError
from pyppeteer.browser import Browser
from pyppeteer.element_handle import ElementHandle

import pytesseract
from PIL import Image

logger = logging.getLogger('rarbg')
WAIT_UNTIL_NETWORKIDLE0 = {'waitUntil': ['load', 'networkidle0']}
WAIT_UNTIL_NETWORKIDLE2 = {'waitUntil': ['load', 'networkidle2']}
WAIT_TIMEOUT_30 = {'timeout': 30 * 1000}
TYPE_DELAY = {'delay': 100}
VIEWPORT = {'width': 1920, 'height': 1200}


async def print_all_pages_url(browser: Browser):
    pages = await browser.pages()
    for (index, page) in zip(itertools.count(start=1), pages):
        print(f'Page {index}: {page.url}')


async def print_resource_tree(page: Page):
    tree = await page._client.send('Page.getResourceTree')
    pprint(tree)


async def on_request(req):
    now = datetime.datetime.now()
    print(f'{now}: {req.method} Request {req.url}')
    pprint(req.headers)


async def on_response(rsp):
    now = datetime.datetime.now()
    print(f'{now}: Response {rsp.url}')


async def on_close(page):
    print(f'page closed, url: {page.url}')


async def do_screenshot(page, filename):
    await page.screenshot({'path': filename + '.png'})


async def is_at_verify_page(page):
    img = await page.querySelector('body > div > div > img:nth-child(7)')
    result = img is not None
    print(f'is at verify page: {result}')
    return result


async def is_at_captcha_page(page):
    img = await page.querySelector(
        'body > form > div > div > table:nth-child(1) > tbody > tr:nth-child(2) > td:nth-child(2) > img'
    )
    result = img is not None
    print(f'is at captcha page: {result}')
    return result


async def is_at_wrong_captcha_page(page):
    warning_message = await page.querySelector(
        'body > form > div > div > table:nth-child(1) > tbody > tr:nth-child(2) > td:nth-child(2) > p'
    )
    result = warning_message is not None
    print(f'is at wrong captcha page: {result}')
    return result


async def handle_top_level_div(page: Page):
    await has_top_level_div(page)
    await page.evaluate('''
    () => {
        function removeSelf(e) {
            e.parentNode.removeChild(e);
        }
        var as = document.querySelectorAll("a");
        for(var i = 0; i < as.length; i++)
        {
            var a = as[i];
            if (a.href.startsWith('https://s4yx'))
            {
                removeSelf(a.parentNode);
            }
        }
    }
    ''')


async def has_top_level_div(page):
    hrefs = await page.JJeval('a', 'as => as.map(a=>a.href)')
    for href in hrefs:
        if href.startswith('https://s4yx'):
            print('Has top level div')
            return True
    return False


def enable_tracing_request(page):
    page.on('request', on_request)
    page.on('response', on_response)


async def get_torrent_pages(page):
    #await page.evaluate('''
    #() => {
    #    var as = document.querySelectorAll("a");
    #    for(var i = 0; i < as.length; i++)
    #    {
    #        var a = as[i];
    #        if (a.href.includes('/torrent/') && !a.href.includes('#comments'))
    #        {
    #            console.log(a.href);
    #            //var tr = a.parentNode.parentNode;
    #            //tr.removeChild(a.parentNode);
    #        }
    #    }
    #}
    #''')
    #sys.exit(0)
    trs_selector = 'body > table:nth-child(6) > tbody > tr > td:nth-child(2) > div > table > tbody > tr:nth-child(2) > td > table.lista2t > tbody > tr.lista2'
    trs = await page.JJ(trs_selector)
    urls = []
    for tr in trs:
        url = await tr.Jeval('td:nth-child(2) > a:nth-child(1)', 'a => a.href')
        urls.append(url)
    return urls


async def get_magnet_link_from_torrent_page(page: Page, browser: Browser,
                                            url: str):
    await handle_top_level_div(page)
    await page.goto(url, options={'waitUntil': ['load', 'domcontentloaded']})
    magnet_links = await page.JJeval('a', 'as => as.map(a => a.href)')
    magnet_links = list(filter(lambda l: l.startswith('magnet'), magnet_links))
    assert len(magnet_links) != 0
    await asyncio.wait([page.goBack(), page.waitForNavigation()])
    return magnet_links[0]


def enable_logging():
    root = logging.getLogger()
    fh = logging.FileHandler('/tmp/pyppeteer.log')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s [%(filename)s:%(levelno)s %(funcName)s]: %(message)s')
    fh.setFormatter(formatter)
    root.addHandler(fh)
    root.setLevel(logging.DEBUG)


async def get_ws_url():
    import json
    import requests
    #info_url = 'http://192.168.1.123:2222/json/version'
    info_url = 'http://127.0.0.1:2222/json/version'
    loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, requests.get, info_url)
    print(resp.text)

    info = json.loads(resp.text)
    return info['webSocketDebuggerUrl']


async def main():
    #enable_logging()
    print('*' * 80)
    #browser: Browser = await pyppeteer.launch()
    url = await get_ws_url()
    browser: Browser = await pyppeteer.connect({
        'browserWSEndpoint': url,
        'defaultViewport': VIEWPORT,
    })
    print('Connected to browser')
    while True:
        page: Page = await bypass_captcha(browser)
        if page is None:
            continue
        print('Passed captcha, ready to proceed')
        break

    search_input_selector = '#searchinput'
    search_button_selector = '#searchTorrent > table > tbody > tr:nth-child(1) > td:nth-child(2) > button'
    await handle_top_level_div(page)

    await page.type(
        selector=search_input_selector,
        text=sys.argv[1],
    )
    await handle_top_level_div(page)
    await asyncio.wait(
        [page.click(search_button_selector),
         page.waitForNavigation()])
    urls = await get_torrent_pages(page)
    for url in urls:
        magnet_link = await get_magnet_link_from_torrent_page(
            page, browser, url)
        print(magnet_link)
        await handle_top_level_div(page)
    #await browser.close()


async def bypass_captcha(browser: Browser):
    page: Page = await browser.newPage()
    #ctx = await browser.createIncognitoBrowserContext()
    #page: Page = await ctx.newPage()
    #await page.setViewport({'width': 1920, 'height': 1200})
    await page.goto('http://rarbg.to', options=WAIT_UNTIL_NETWORKIDLE0)
    await handle_top_level_div(page)

    torrents_selector = 'body > table:nth-child(5) > tbody > tr > td > table > tbody > tr > td:nth-child(3) > a'
    print('Do real torrents click')
    await page.click(selector=torrents_selector)
    print('nav by click torrents')

    if await is_at_verify_page(page):
        await page.waitForNavigation(WAIT_UNTIL_NETWORKIDLE0)
        if await is_at_captcha_page(page):
            if await handle_captcha(page):
                return page
            else:
                await page.close()
                return None
    else:
        print('no verify page')
        return page

    assert False
    return None


async def handle_captcha(page: Page):
    tree = await page._client.send('Page.getResourceTree')
    for resource in tree['frameTree']['resources']:
        if resource['type'] == 'Image' and 'threat_captcha' in resource['url']:
            url = resource['url']
            break
    assert url is not None
    print(f'Captcha url: {url}')

    params = {'frameId': tree['frameTree']['frame']['id'], 'url': url}
    result = await page._client.send('Page.getResourceContent', params)
    assert result['base64Encoded']
    content = base64.b64decode(result['content'])
    with open('captcha.png', 'wb') as fp:
        fp.write(content)

    text = pytesseract.image_to_string(Image.open('captcha.png'))
    text = re.sub(' ', '', text)
    print(f'Captcha: {text}')

    input_selector = '#solve_string'
    await page.type(selector=input_selector, text=text, options=TYPE_DELAY)
    await asyncio.wait(
        [page.click(selector='#button_submit'),
         page.waitForNavigation()])
    return not await is_at_wrong_captcha_page(page)

    #TODO(jacobwpeng): Loop at captcha page
    #await page.waitForNavigation(WAIT_UNTIL_NETWORKIDLE0)
    #assert await is_at_verify_page(page)
    #await page.waitForNavigation(options={'timeout': 3000})
    #print(f'nav by wrong captcha verify')
    #assert await is_at_captcha_page(page)


asyncio.get_event_loop().run_until_complete(main())
