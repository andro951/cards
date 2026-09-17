import io

from PIL import Image

from foundry.images import trim_transparent_edges


def test_transparent_edge_crop_ignores_alpha_two_strays():
    im=Image.new('RGBA',(12,10),(0,0,0,0))
    # Nearly invisible junk in the outer padding must not hold the crop open.
    im.putpixel((0,0),(255,0,0,1))
    im.putpixel((11,9),(0,255,0,2))
    # Real retained content.
    for y in range(3,8):
        for x in range(4,9):
            im.putpixel((x,y),(10,20,30,255))

    cropped=trim_transparent_edges(im)

    assert cropped.size==(5,5)
    assert cropped.getpixel((0,0))==(10,20,30,255)
    assert cropped.getpixel((4,4))==(10,20,30,255)


def test_transparent_edge_crop_keeps_alpha_three_boundary():
    im=Image.new('RGBA',(8,8),(0,0,0,0))
    im.putpixel((1,2),(20,30,40,3))
    im.putpixel((6,5),(50,60,70,255))

    cropped=trim_transparent_edges(im)

    assert cropped.size==(6,4)
    assert cropped.getpixel((0,0))==(20,30,40,3)
    assert cropped.getpixel((5,3))==(50,60,70,255)


def test_transparent_edge_crop_does_not_erase_low_alpha_inside_crop():
    im=Image.new('RGBA',(7,7),(0,0,0,0))
    im.putpixel((2,2),(100,110,120,255))
    im.putpixel((4,4),(130,140,150,255))
    im.putpixel((3,3),(200,210,220,2))

    cropped=trim_transparent_edges(im)

    assert cropped.size==(3,3)
    # The alpha threshold is only for finding the outer bounds; interior pixels
    # are preserved byte-for-byte.
    assert cropped.getpixel((1,1))==(200,210,220,2)
