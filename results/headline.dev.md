corpus: dev

policy         net value  exact acc  false pays  coverage  auto precision  over-esc  wall
-------------  ---------  ---------  ----------  --------  --------------  --------  ----
reckless       -111000    25.0%      45          100.0%    25.0%           0         0.0s
reckless+gate  +1635      80.0%      0           25.0%     100.0%          12        0.0s
baseline       -58115     50.0%      24          71.7%     44.2%           6         0.0s
baseline+gate  +2155      86.7%      0           31.7%     100.0%          8         0.0s
rules-only     -11895     90.0%      6           55.0%     81.8%           0         0.0s
guarded        +3195      100.0%     0           45.0%     100.0%          0         0.0s

net value under different false-pay penalties (the ranking should not depend on the exact weight):

policy         pen=-250  pen=-600  pen=-1200  pen=-2500  pen=-5000  pen=-12000
-------------  --------  --------  ---------  ---------  ---------  ----------
reckless       -9750     -25500    -52500     -111000    -223500    -538500
reckless+gate  +1635     +1635     +1635      +1635      +1635      +1635
baseline       -4115     -12515    -26915     -58115     -118115    -286115
baseline+gate  +2155     +2155     +2155      +2155      +2155      +2155
rules-only     +1605     -495      -4095      -11895     -26895     -68895
guarded        +3195     +3195     +3195      +3195      +3195      +3195
