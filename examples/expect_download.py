import asyncio
import base64
import pathlib

import zendriver as zd


async def main() -> None:
    path_image = r'Your Image Path'
    out_dir = r'.'
    async with await zd.start() as browser:
        page = browser.main_tab
        await page.get('https://translate.yandex.com/en/ocr')
        await (await page.select('input[type="file"]')).send_file(path_image)
        await asyncio.sleep(3)

        async with page.expect_download() as download_ex:
            await (await page.select('#downloadButton')).mouse_click()
            download = await download_ex.value
        print(download.suggested_filename)
        with pathlib.Path(out_dir, download.suggested_filename).open('wb') as fw:
            bytes_file = base64.b64decode(download.url.split(',', 1)[-1])
            fw.write(bytes_file)


if __name__ == '__main__':
    asyncio.run(main())
