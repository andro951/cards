"""Report browser alpha-edge rounding and make a serial/worker review sheet."""
import json
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw

def main():
    root=Path(__file__).resolve().parents[1]/'test-results/user-deck-workers'
    targets=json.loads((root/'prepared.json').read_text())['data'];stats=[]
    for target in targets:
        with Image.open(root/'serial'/(target['key']+'.png')) as left,Image.open(root/'workers'/(target['key']+'.png')) as right:
            channels=ImageChops.difference(left.convert('RGBA'),right.convert('RGBA')).split();maximum=channels[0]
            for channel in channels[1:]:maximum=ImageChops.lighter(maximum,channel)
            histogram=maximum.histogram();pixels=left.width*left.height
            stats.append({'name':target['name'],'changedFraction':sum(histogram[1:])/pixels,'visibleDifferenceFraction':sum(histogram[5:])/pixels,'maxChannelDifference':max(i for i,n in enumerate(histogram) if n)})
    (root/'pixel-metrics.json').write_text(json.dumps(stats,indent=2))
    assert all(row['changedFraction']<.05 and row['visibleDifferenceFraction']<.001 for row in stats),stats
    print(sorted(stats,key=lambda row:-row['visibleDifferenceFraction'])[:15])
    selected=[target for target in targets if target['name'] in ['Fighter Class',"Urza's Saga",'Stoneforge Mystic','Day','Spirit','Takenuma, Abandoned Mire']]
    output=Image.new('RGB',(1200,900),'#222');draw=ImageDraw.Draw(output)
    for index,target in enumerate(selected):
        for column,mode in enumerate(['serial','workers']):
            position=((index%3)*400+column*200,(index//3)*300)
            with Image.open(root/mode/(target['key']+'.png')) as image:output.paste(image.convert('RGB').resize((200,280)),position)
            draw.text((position[0],position[1]+280),target['name']+' '+mode,fill='white')
    output.save(root/'review.png')

if __name__=='__main__':main()
