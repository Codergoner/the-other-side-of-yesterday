"""Generate seamless, original PBR texture tiles for the playable harbor."""
from pathlib import Path
import json
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'/'game'/'textures'; OUT.mkdir(parents=True,exist_ok=True)
N=512
rng=np.random.default_rng(912)
y,x=np.mgrid[0:N,0:N]/N

def noise(scale):
    a=rng.normal(size=(N,N))
    fy=np.fft.fftfreq(N)[:,None]; fx=np.fft.fftfreq(N)[None,:]
    filt=np.exp(-(fx*fx+fy*fy)*scale*scale*2)
    b=np.fft.ifft2(np.fft.fft2(a)*filt).real
    return (b-b.mean())/max(b.std(),1e-6)

coarse=noise(70); medium=noise(16); fine=noise(2)
stone_row=np.floor(y*5)
stone_x=(x*3+(stone_row%2)*.5)%1
stone_y=(y*5)%1
seam=(np.minimum(stone_x,1-stone_x)<.035)|(np.minimum(stone_y,1-stone_y)<.045)
block_id=np.floor(x*3+(stone_row%2)*.5)+stone_row*3
block_variation=np.sin(block_id*41.7)*.06

specs={
 'M_Plaster':((.76,.68,.51),'plaster',.86,0),
 'M_Stone':((.56,.50,.39),'stone',.89,0),
 'M_Rock':((.49,.47,.41),'rock',.95,0),
 'M_Cobble':((.45,.43,.37),'stone',.94,0),
 'M_Wood':((.26,.145,.067),'wood',.78,0),
 'M_Roof':((.13,.29,.27),'roof',.73,0),
 'M_Dark':((.055,.06,.052),'plain',.93,0),
 'M_Metal':((.14,.135,.11),'metal',.54,.7),
 'M_Leaf':((.25,.34,.08),'leaf',.83,0),
 'M_Fabric':((.67,.52,.33),'fabric',.91,0),
 'M_Water':((.035,.20,.25),'water',.16,.05),
 'M_Terracotta':((.56,.25,.12),'plaster',.84,0),
 'M_CanvasBlue':((.17,.30,.34),'fabric',.90,0),
 'M_CanvasRust':((.50,.23,.12),'fabric',.91,0),
 'M_FruitGold':((.90,.49,.075),'plain',.49,0),
 'M_FruitRed':((.58,.075,.028),'plain',.48,0),
 'M_FruitGreen':((.27,.40,.085),'plain',.55,0),
}
manifest={}
for name,(color,kind,roughness,metallic) in specs.items():
    detail=coarse*.035+medium*.025+fine*.008
    height=medium*.08+fine*.025
    if kind=='stone':
        detail+=block_variation-np.where(seam,.14,0)
        height+=np.where(seam,-.5,.18)+block_variation
    elif kind=='plaster':
        chips=coarse+medium*.3>1.5
        crack=np.abs(np.sin(x*18.85+coarse*.35+y*6.28))<.018
        detail-=chips*.10+crack*.18
        height-=chips*.20+crack*.18
    elif kind=='rock':
        fissure=np.abs(np.sin(x*12.566+coarse*.3+y*6.283))<.035
        detail+=coarse*.045-fissure*.07
        height+=coarse*.28+medium*.12-fissure*.15
    elif kind=='wood':
        grain=np.sin(x*2*np.pi*32+medium*.4+np.sin(y*2*np.pi)*3)
        plank=(np.minimum((x*4)%1,1-(x*4)%1)<.016)
        detail+=grain*.025-plank*.13
        height+=grain*.045-plank*.22
    elif kind=='roof':
        tx=(x*8)%1; ty=(y*7)%1
        height=np.sin(tx*np.pi)*.65+(ty>.1)*.18+fine*.025
        detail+=np.sin(tx*np.pi)*.04-(ty<.035)*.12
    elif kind=='fabric':
        weave=np.sin(x*2*np.pi*80)*np.sin(y*2*np.pi*80)
        height=weave*.06+medium*.025
        detail+=weave*.018
    elif kind=='metal':
        detail+=np.clip(coarse-.6,0,2)*.07
        height=medium*.025+fine*.008
    elif kind=='water':
        height=np.sin(x*np.pi*32+np.sin(y*np.pi*8))*.13+medium*.07
        detail*=.25
    elif kind=='leaf':
        height=medium*.08
        detail+=np.sin(x*np.pi*16+y*np.pi*8)*.02
    rgb=np.clip(np.asarray(color)[None,None,:]+detail[:,:,None],0,1)
    rr=np.clip(roughness+medium*.025,0,1)
    dx=(np.roll(height,-1,axis=1)-np.roll(height,1,axis=1))*3
    dy=(np.roll(height,-1,axis=0)-np.roll(height,1,axis=0))*3
    normal=np.stack([-dx,-dy,np.ones_like(dx)],axis=-1)
    normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
    Image.fromarray(np.uint8(rgb*255),'RGB').save(OUT/(name+'_BaseColor.png'))
    Image.fromarray(np.uint8(rr*255),'L').save(OUT/(name+'_Roughness.png'))
    Image.fromarray(np.uint8((normal*.5+.5)*255),'RGB').save(OUT/(name+'_Normal.png'))
    manifest[name]={'base_color':name+'_BaseColor.png','roughness':name+'_Roughness.png','normal':name+'_Normal.png','metallic':metallic,'roughness_scalar':roughness,'tile_metres':2 if kind in ('plaster','stone') else 1}
(OUT/'materials.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Generated',len(manifest),'PBR materials and',len(manifest)*3,'seamless texture maps')
