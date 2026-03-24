# Test Image Attribution

`test_raw.jpg` is a test fixture downloaded from Wikimedia Commons.

Source file page:
- https://commons.wikimedia.org/wiki/File:2017.06.11_Equality_March_2017,_Washington,_DC_USA_6568_(34427675284).jpg

Direct file used for this fixture:
- https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/2017.06.11_Equality_March_2017%2C_Washington%2C_DC_USA_6568_%2834427675284%29.jpg/1280px-2017.06.11_Equality_March_2017%2C_Washington%2C_DC_USA_6568_%2834427675284%29.jpg

Title:
- `2017.06.11 Equality March 2017, Washington, DC USA 6568 (34427675284).jpg`

Author:
- Ted Eytan

License:
- CC BY-SA 2.0
- https://creativecommons.org/licenses/by-sa/2.0/

Notes for repository use:
- The base fixture is stored under the local filename `test_raw.jpg`.
- Derived test fixtures may use the same base name with a varying suffix pattern like `test_***.jpg`, depending on the use case.
- The current repository fixtures include:
  - `test_acd.jpg` for ACDSee face metadata
  - `test_mic.jpg` and `test_mic.xmp` for Microsoft People Tagging; the Microsoft metadata is also embedded in `test_mic.jpg`
  - `test_pic.jpg` and `test_pic.xmp` as the main `MWG_REGIONS` fixture
  - `test_dig.jpg` for a real digiKam-written example using MWG face regions, including `AppliedToDimensions`
- This repository currently includes the 1280px Wikimedia derivative under the original license.
- Additional metadata may be added to this file for test purposes. Those metadata values do not necessarily originate from the original image or the original publication context.
- Attribution, source link, author name, and license link should remain with the file when redistributed.
- If the image is modified further, those changes should be indicated and the ShareAlike terms of CC BY-SA 2.0 must still be respected.
