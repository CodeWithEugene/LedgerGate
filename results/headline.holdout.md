corpus: holdout

policy         net value  exact acc  false pays  coverage  auto precision  over-esc  wall
-------------  ---------  ---------  ----------  --------  --------------  --------  ----
reckless       -111000    25.0%      45          100.0%    25.0%           0         0.0s
reckless+gate  +1635      80.0%      0           25.0%     100.0%          12        0.0s
baseline       -57985     51.7%      24          73.3%     45.5%           5         0.0s
baseline+gate  +2285      88.3%      0           33.3%     100.0%          7         0.0s
rules-only     -11895     90.0%      6           55.0%     81.8%           0         0.0s
guarded        +3195      100.0%     0           45.0%     100.0%          0         0.0s

net value under different false-pay penalties (the ranking should not depend on the exact weight):

policy         pen=-250  pen=-600  pen=-1200  pen=-2500  pen=-5000  pen=-12000
-------------  --------  --------  ---------  ---------  ---------  ----------
reckless       -9750     -25500    -52500     -111000    -223500    -538500
reckless+gate  +1635     +1635     +1635      +1635      +1635      +1635
baseline       -3985     -12385    -26785     -57985     -117985    -285985
baseline+gate  +2285     +2285     +2285      +2285      +2285      +2285
rules-only     +1605     -495      -4095      -11895     -26895     -68895
guarded        +3195     +3195     +3195      +3195      +3195      +3195
