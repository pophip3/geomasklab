"""Procedural illustrative fixtures. These are neither EO data nor predictions."""
from pathlib import Path
from PIL import Image, ImageDraw


def fixture(sample):
    size = (800, 600) if sample == 'urban' else (800, 800)
    image = Image.new('RGB', size, '#dee7eb')
    draw = ImageDraw.Draw(image)
    mask = Image.new('L', size, 0)
    truth = ImageDraw.Draw(mask)
    if sample == 'urban':
        draw.rectangle((0,260,799,340), fill='#526574')
        draw.rectangle((370,0,430,599), fill='#526574')
        for x,y,w,h in [(70,70,110,100),(250,110,70,95),(480,70,115,90),
                        (650,120,90,100),(60,400,110,100),(240,390,85,110),
                        (485,420,85,100),(635,410,100,95)]:
            box = (x,y,x+w-1,y+h-1)
            draw.rectangle(box, fill='#b78858', outline='#61482d', width=3)
            truth.rectangle(box, fill=255)
    else:
        draw.rectangle((0,340,799,760), fill='#697c88')
        for cx in (220,610):
            polygon=[(cx,410),(cx+12,440),(cx+12,510),(cx+100,535),
                     (cx+100,555),(cx+10,550),(cx+8,625),(cx+40,645),
                     (cx+40,655),(cx,645),(cx-40,655),(cx-40,645),
                     (cx-8,625),(cx-10,550),(cx-100,555),(cx-100,535),
                     (cx-12,510),(cx-12,440)]
            draw.polygon(polygon, fill='#edf2f5', outline='#273b4b')
            truth.polygon(polygon, fill=255)
    draw.rectangle((0,0,799,35), fill='#12364b')
    draw.text((14,12),'SYNTHETIC FIXTURE / NO MODEL INFERENCE / PIXEL COORDINATES',fill='white')
    return image, mask


def write_assets(destination=None):
    directory = Path(destination) if destination else Path(__file__).parent / 'web/assets'
    directory.mkdir(parents=True, exist_ok=True)
    for sample, filename in [('urban','urban.png'),('airport','airport.jpg')]:
        image, _ = fixture(sample)
        image.save(directory / filename)


if __name__ == '__main__':
    write_assets()
