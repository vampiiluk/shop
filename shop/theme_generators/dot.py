"""Dot: technical monochrome storefront. Dot grid canvas, floating capsule nav, rounded panels, mono spec labels."""

from shop.theme_generators.blocks import (
	WHATSAPP_GREEN,
	block,
	component_ref,
	dv,
	repeater,
	root,
	upsert_client_script,
	upsert_component,
	upsert_page,
	upsert_variables,
	whatsapp_icon,
)

GROUP = "dot"
HEAD = "Space Grotesk"
MONO = "DM Mono"

# Wordmark: lowercase "rel" + a lemniscate for "oo" + "p".
# The source file shipped with an internal `prefers-color-scheme` rule that
# flipped the fill to #fff. This storefront renders light on every device (the
# dark palette is never emitted), so that rule rendered the logo white-on-white
# for anyone with dark mode enabled. The media query and the .glyph class are
# therefore dropped and the path is filled with currentColor, which inherits
# refs["ink"] like the rest of the header.
LOGO_VIEWBOX = "0 0 3570 1212"
LOGO_PATH = (
	"M 2997.75 330.00 C 2993.66 332.34 2994.00 329.20 2994.00 326.00 C 2994.00 302.33 2994.00 "
	"278.67 2994.00 255.00 C 2992.06 251.61 2978.46 253.00 2974.00 253.00 C 2852.67 253.00 "
	"2731.33 253.00 2610.00 253.00 C 2603.10 253.86 2620.59 262.24 2623.00 263.75 C 2635.28 "
	"271.42 2646.06 281.79 2658.00 289.25 C 2664.76 293.48 2672.25 302.25 2678.00 308.00 C "
	"2692.53 322.53 2708.90 339.64 2719.75 357.00 C 2726.52 367.83 2732.70 380.53 2740.00 390.75 "
	"C 2752.59 392.32 2767.56 392.55 2780.00 391.00 C 2799.64 388.55 2822.99 391.00 2843.00 "
	"391.00 C 2848.23 393.61 2847.00 404.54 2847.00 410.00 C 2847.00 663.00 2847.00 916.00 "
	"2847.00 1169.00 C 2847.48 1172.36 2858.51 1171.00 2862.00 1171.00 C 2907.00 1171.00 2952.00 "
	"1171.00 2997.00 1171.00 C 2999.50 1170.64 2999.00 1170.50 2999.00 1168.00 C 2999.00 1156.67 "
	"2999.00 1145.33 2999.00 1134.00 C 2999.00 1035.00 2999.00 936.00 2999.00 837.00 C 2999.76 "
	"830.93 3015.58 848.58 3019.00 852.00 C 3034.11 867.11 3052.02 878.01 3070.00 889.25 C "
	"3097.80 906.62 3133.36 915.04 3165.00 919.00 C 3174.48 920.19 3184.57 918.82 3194.00 920.00 "
	"C 3221.71 923.46 3249.04 916.37 3276.00 913.00 C 3300.64 909.92 3327.73 898.38 3350.00 "
	"887.25 C 3454.83 834.83 3512.98 731.19 3527.00 619.00 C 3536.85 540.22 3516.92 452.48 "
	"3474.75 385.00 C 3455.33 353.93 3429.37 327.95 3402.00 304.00 C 3372.47 278.16 3334.95 "
	"263.73 3299.00 250.25 C 3271.99 240.12 3237.05 238.00 3208.00 238.00 C 3199.74 238.00 "
	"3190.10 236.99 3182.00 238.00 C 3168.98 239.63 3155.92 242.38 3143.00 244.00 C 3094.62 "
	"250.05 3024.07 287.88 2997.75 330.00 Z  M 3170.00 379.75 C 3180.64 375.76 3202.90 379.61 "
	"3214.00 381.00 C 3285.68 389.96 3337.20 438.20 3362.25 505.00 C 3368.73 522.29 3374.00 "
	"542.48 3374.00 561.00 C 3374.00 585.07 3376.34 613.10 3367.75 636.00 C 3361.84 651.75 "
	"3357.93 668.31 3348.75 683.00 C 3318.04 732.13 3264.13 779.00 3203.00 779.00 C 3100.28 "
	"791.84 2998.00 699.31 2998.00 596.00 C 2990.67 537.33 3014.72 479.75 3053.00 436.00 C "
	"3059.23 428.88 3066.89 420.32 3075.00 415.25 C 3107.24 395.10 3132.64 384.42 3170.00 379.75 "
	"Z  M 1825.00 238.25 C 1818.99 240.50 1809.55 239.18 1803.00 240.00 C 1790.97 241.50 1779.04 "
	"244.49 1767.00 246.00 C 1756.01 247.37 1742.42 251.84 1732.00 255.75 C 1691.64 270.89 "
	"1653.05 288.08 1620.00 317.00 C 1450.64 465.19 1461.70 745.19 1657.00 867.25 C 1672.42 "
	"878.82 1694.00 888.50 1712.00 895.25 C 1807.97 931.24 1911.40 929.05 2004.00 882.75 C "
	"2043.58 862.96 2087.47 809.18 2134.00 815.00 C 2167.22 819.15 2199.12 853.33 2227.00 870.75 "
	"C 2259.81 891.26 2304.93 910.24 2343.00 915.00 C 2357.93 916.87 2373.05 917.13 2388.00 "
	"919.00 C 2399.55 920.44 2414.28 921.22 2426.00 919.75 C 2430.92 917.90 2436.82 919.65 "
	"2442.00 919.00 C 2455.33 917.33 2468.68 914.66 2482.00 913.00 C 2526.54 907.43 2587.09 "
	"878.68 2621.00 849.00 C 2658.69 816.02 2700.68 774.20 2718.75 726.00 C 2732.64 688.96 "
	"2744.10 656.18 2749.00 617.00 C 2764.83 490.36 2704.32 358.07 2595.00 289.75 C 2584.24 "
	"284.37 2573.72 277.61 2563.00 272.25 C 2546.55 264.03 2529.10 258.66 2512.00 252.25 C "
	"2497.41 246.78 2479.36 243.92 2464.00 242.00 C 2402.38 234.30 2342.39 237.85 2284.00 259.75 "
	"C 2271.66 264.38 2257.27 269.21 2246.00 276.25 C 2231.03 285.61 2215.98 294.88 2201.00 "
	"304.25 C 2172.59 322.00 2155.62 346.70 2118.00 342.00 C 2087.40 338.18 2060.51 308.20 "
	"2035.00 292.25 C 1985.18 261.11 1937.79 247.10 1881.00 240.00 C 1863.77 237.85 1842.58 "
	"236.05 1825.00 238.25 Z  M 1839.00 378.75 C 1846.86 375.80 1862.68 378.96 1871.00 380.00 C "
	"1904.41 384.18 1928.51 396.44 1957.00 414.25 C 1964.26 418.79 1970.54 426.34 1977.00 432.00 "
	"C 1987.42 441.12 1998.22 449.38 2010.00 456.75 C 2038.49 474.55 2072.49 484.94 2105.00 "
	"489.00 C 2153.40 495.05 2204.35 479.16 2245.00 453.75 C 2262.63 442.73 2275.91 425.93 "
	"2293.00 415.25 C 2325.83 394.73 2357.72 379.00 2397.00 379.00 C 2427.59 379.00 2458.25 "
	"381.38 2486.00 395.25 C 2595.84 450.17 2628.03 590.75 2564.75 692.00 C 2553.09 710.66 "
	"2538.38 724.67 2522.00 739.00 C 2493.19 764.21 2449.76 780.00 2412.00 780.00 C 2375.18 "
	"780.00 2337.54 770.46 2306.00 750.75 C 2279.53 734.21 2257.96 711.10 2231.00 694.25 C "
	"2204.09 677.43 2170.28 672.78 2140.00 669.00 C 2098.59 663.82 2045.06 679.34 2010.00 701.25 "
	"C 1982.77 718.27 1960.34 740.66 1933.00 757.75 C 1908.91 772.81 1880.02 776.62 1853.00 "
	"780.00 C 1829.18 780.00 1805.21 778.08 1783.00 769.75 C 1696.94 737.48 1643.72 646.22 "
	"1655.00 556.00 C 1657.63 534.97 1663.28 516.92 1670.75 497.00 C 1681.81 467.50 1708.31 "
	"429.93 1735.00 413.25 C 1758.20 398.75 1783.63 384.42 1811.00 381.00 C 1820.28 379.84 "
	"1829.71 379.91 1839.00 378.75 Z  M 195.75 340.00 C 194.88 340.87 193.50 343.18 192.25 341.00 "
	"C 190.92 338.67 192.00 327.25 192.00 324.00 C 192.00 302.24 194.42 277.38 191.75 256.00 C "
	"189.48 251.46 184.55 253.00 180.00 253.00 C 134.00 253.00 88.00 253.00 42.00 253.00 C 37.31 "
	"255.34 39.00 263.15 39.00 268.00 C 39.00 481.00 39.00 694.00 39.00 907.00 C 41.71 910.38 "
	"52.47 909.00 57.00 909.00 C 101.67 909.00 146.33 909.00 191.00 909.00 C 194.11 907.22 193.00 "
	"903.43 193.00 900.00 C 193.00 834.67 193.00 769.33 193.00 704.00 C 193.00 611.97 177.70 "
	"488.77 254.00 422.00 C 271.89 406.35 295.04 391.99 319.00 389.00 C 346.40 385.57 371.16 "
	"382.69 398.00 392.75 C 405.71 395.64 415.24 397.68 422.00 402.75 C 426.41 402.75 427.94 "
	"396.63 429.75 393.00 C 441.87 368.76 456.39 343.97 470.75 321.00 C 479.00 307.80 485.44 "
	"292.41 494.75 280.00 C 494.75 271.02 447.38 252.27 438.00 248.75 C 350.46 215.92 238.55 "
	"254.39 195.75 340.00 Z  M 1094.00 803.00 C 1095.84 799.32 1093.65 798.65 1091.00 796.00 C "
	"1062.54 767.54 1030.32 740.78 1000.00 714.25 C 998.93 714.12 998.09 713.70 997.00 714.25 C "
	"990.94 717.28 981.52 728.17 976.00 733.00 C 964.96 742.66 951.43 749.98 939.00 757.75 C "
	"922.22 768.24 895.29 777.59 876.00 780.00 C 862.45 781.69 848.69 784.29 835.00 786.00 C "
	"825.46 787.19 813.33 786.17 804.00 785.00 C 794.00 783.75 783.98 783.25 774.00 782.00 C "
	"741.64 777.95 707.18 758.16 683.00 737.00 C 658.93 715.94 643.89 690.70 632.75 661.00 C "
	"630.08 653.88 626.00 643.58 626.00 636.00 C 626.46 632.32 627.80 633.00 631.00 633.00 C "
	"648.67 633.00 666.33 633.00 684.00 633.00 C 836.33 633.00 988.67 633.00 1141.00 633.00 C "
	"1148.87 628.50 1145.00 572.89 1145.00 562.00 C 1145.00 542.07 1139.40 524.20 1137.00 505.00 "
	"C 1129.44 444.53 1093.74 383.42 1054.00 338.00 C 1041.89 324.16 1027.53 313.84 1014.00 "
	"302.00 C 1000.87 290.51 978.48 276.43 962.00 270.25 C 946.30 264.36 930.71 258.14 915.00 "
	"252.25 C 891.97 243.61 863.30 241.04 839.00 238.00 C 826.74 236.47 811.06 236.49 799.00 "
	"238.00 C 792.21 238.85 784.79 237.15 778.00 238.00 C 758.87 240.39 733.95 241.52 716.00 "
	"248.25 C 691.82 257.32 664.46 262.21 642.00 276.25 C 628.67 284.58 615.30 292.94 602.00 "
	"301.25 C 590.21 308.62 580.44 319.86 570.00 329.00 C 537.25 357.65 509.58 401.12 494.25 "
	"442.00 C 448.12 565.01 465.71 713.10 554.00 814.00 C 577.86 841.27 606.78 859.86 637.00 "
	"878.75 C 678.79 904.87 730.97 913.12 778.00 919.00 C 816.30 923.79 853.48 919.69 891.00 "
	"915.00 C 902.88 913.51 916.74 911.47 928.00 907.25 C 941.46 902.20 956.21 898.92 970.00 "
	"893.75 C 1004.64 880.76 1036.48 859.08 1064.00 835.00 C 1074.28 826.01 1086.74 814.62 "
	"1094.00 803.00 Z  M 988.00 514.00 C 987.21 520.35 956.84 518.00 950.00 518.00 C 843.33 "
	"518.00 736.67 518.00 630.00 518.00 C 622.17 514.09 639.02 476.46 642.75 469.00 C 704.87 "
	"344.76 890.31 337.30 963.25 454.00 C 973.50 470.40 985.60 494.81 988.00 514.00 Z  M 1248.00 "
	"40.25 C 1244.89 45.70 1247.00 65.73 1247.00 73.00 C 1247.00 113.00 1247.00 153.00 1247.00 "
	"193.00 C 1247.00 310.00 1247.00 427.00 1247.00 544.00 C 1247.00 615.95 1243.19 690.53 "
	"1252.00 761.00 C 1256.75 798.97 1275.62 840.29 1305.00 866.00 C 1363.57 917.25 1433.12 "
	"912.00 1506.00 912.00 C 1555.67 912.00 1605.33 912.00 1655.00 912.00 C 1661.75 912.00 "
	"1646.95 905.47 1645.00 904.25 C 1634.86 897.91 1623.00 891.88 1614.00 884.00 C 1605.67 "
	"876.71 1596.36 870.32 1588.00 863.00 C 1572.24 849.21 1558.63 832.58 1545.00 817.00 C "
	"1536.97 807.82 1528.75 796.39 1522.25 786.00 C 1520.65 783.44 1516.43 775.47 1514.00 774.25 "
	"C 1510.53 772.52 1496.53 774.00 1492.00 774.00 C 1462.81 774.00 1429.17 777.68 1411.25 "
	"749.00 C 1398.36 728.38 1400.00 698.63 1400.00 675.00 C 1400.00 645.00 1400.00 615.00 "
	"1400.00 585.00 C 1400.00 404.00 1400.00 223.00 1400.00 42.00 C 1398.16 38.79 1392.63 40.00 "
	"1389.00 40.00 C 1342.33 40.00 1295.67 40.00 1249.00 40.00 L 1248.00 40.25 Z"
)

# Compact monogram, used beside the wordmark where the accent dot used to sit:
# "re" stacked over the lemniscate. Tinted with the accent at low opacity, so
# it reads as a secondary mark rather than competing with the wordmark.
#
# The viewBox and the group transform both have to be kept. The paths carry
# coordinates in the thousands and the transform is what maps them into the
# viewBox; dropping it (because it looks like a font-conversion artefact) leaves
# a blank space where the mark should be.
GLYPH_VIEWBOX = "514.6 457.09 768.87 887.91"
GLYPH_TRANSFORM = "translate(0.000000,1800.000000) scale(0.100000,-0.100000)"
GLYPH_PATHS = (
	"M7455 13414 c-44 -8 -93 -20 -110 -25 -16 -6 -43 -14 -60 -19 -103 -28 -270 -110 -355 -174 "
	"-137 -103 -296 -283 -340 -383 -10 -25 -29 -31 -31 -10 0 6 -1 129 -2 272 l-2 260 -565 0 -565 "
	"0 0 -1990 0 -1990 560 -3 c518 -2 561 -1 573 15 9 13 12 233 12 1021 0 650 4 1037 11 1096 37 "
	"313 157 590 329 754 80 76 289 202 335 202 9 0 25 5 36 11 29 15 201 39 284 39 79 0 240 -22 "
	"295 -41 19 -6 62 -24 94 -40 66 -32 75 -30 104 28 9 18 42 74 73 125 31 51 69 116 84 143 45 80 "
	"236 399 250 415 36 43 27 72 -30 100 -11 6 -33 19 -50 29 -114 73 -273 130 -463 166 -104 19 "
	"-357 19 -467 -1z",
	"M10215 13419 c-27 -5 -84 -14 -125 -19 -98 -12 -206 -39 -350 -86 -41 -14 -88 -29 -105 -33 -27 "
	"-7 -91 -34 -185 -79 -76 -37 -290 -168 -365 -226 -134 -101 -303 -280 -404 -426 -71 -102 -86 "
	"-128 -135 -222 -85 -164 -117 -248 -172 -453 -61 -230 -83 -525 -55 -765 16 -147 32 -221 88 "
	"-420 66 -235 221 -522 375 -694 144 -162 307 -299 465 -391 43 -26 85 -51 93 -56 35 -21 220 "
	"-109 230 -109 5 0 18 -4 28 -10 18 -11 89 -36 137 -50 17 -4 44 -13 60 -19 65 -22 236 -59 370 "
	"-81 200 -32 595 -34 810 -4 102 15 134 21 270 54 28 7 66 16 85 20 19 5 49 13 65 19 17 6 59 20 "
	"95 32 36 12 79 27 95 33 41 16 213 103 250 127 17 10 37 22 45 26 72 34 286 201 365 285 86 90 "
	"135 148 135 157 0 11 -58 63 -130 116 -36 26 -69 53 -75 59 -5 6 -30 27 -55 46 -25 19 -98 77 "
	"-164 130 -187 150 -214 170 -228 170 -8 0 -35 -20 -61 -45 -121 -114 -291 -225 -432 -284 -141 "
	"-58 -177 -69 -350 -107 -113 -25 -446 -25 -560 0 -113 24 -281 74 -323 95 -9 5 -37 18 -62 30 "
	"-92 44 -250 162 -318 237 -95 104 -192 264 -227 374 -10 30 -24 74 -32 97 -8 24 -12 47 -8 53 4 "
	"7 541 10 1654 10 1307 0 1651 3 1658 13 20 25 34 297 23 443 -16 218 -65 463 -116 582 -8 18 "
	"-14 41 -14 50 0 10 -7 27 -15 38 -8 10 -15 25 -15 32 0 7 -21 56 -47 110 -167 346 -435 648 "
	"-735 827 -157 93 -316 165 -478 216 -36 11 -85 27 -110 35 -25 8 -54 14 -65 14 -11 0 -49 6 -85 "
	"15 -154 34 -277 45 -511 44 -129 -1 -256 -5 -284 -10z m580 -844 c39 -10 85 -24 103 -31 18 -8 "
	"39 -14 47 -14 7 0 26 -7 42 -15 15 -7 48 -23 73 -35 60 -28 71 -35 160 -101 171 -128 288 -287 "
	"363 -494 33 -93 48 -146 42 -155 -8 -13 -2252 -14 -2260 -1 -3 5 0 31 6 58 53 223 200 442 398 "
	"592 145 110 380 201 556 215 118 9 401 -2 470 -19z",
	"M7050 8635 c-74 -6 -162 -17 -195 -24 -168 -35 -276 -63 -333 -87 -18 -8 -40 -14 -50 -14 -9 0 "
	"-26 -7 -36 -15 -11 -8 -26 -15 -33 -15 -15 0 -134 -57 -218 -105 -33 -19 -67 -37 -75 -41 -8 -4 "
	"-44 -28 -80 -52 -227 -155 -434 -371 -587 -611 -44 -69 -129 -238 -155 -306 -39 -100 -47 -123 "
	"-61 -175 -68 -241 -81 -335 -81 -595 0 -227 7 -294 46 -455 6 -25 14 -61 18 -80 8 -33 14 -52 "
	"45 -140 37 -102 117 -277 158 -345 152 -251 418 -527 667 -690 87 -57 287 -160 365 -188 304 "
	"-108 520 -147 820 -147 240 0 547 48 683 106 18 8 40 14 50 14 9 0 26 7 36 15 11 8 26 15 34 15 "
	"17 0 259 119 307 150 17 11 37 23 45 27 12 6 178 125 230 166 122 95 227 137 345 137 126 0 198 "
	"-32 375 -165 210 -158 474 -306 615 -345 17 -5 44 -13 60 -18 390 -134 960 -134 1350 0 17 5 44 "
	"14 60 18 76 22 288 118 380 173 159 96 314 223 459 376 28 30 58 62 67 71 8 9 42 52 76 96 93 "
	"123 137 194 204 334 22 47 45 93 50 102 14 27 40 99 49 138 4 19 13 49 18 65 16 45 38 139 58 "
	"245 25 136 25 515 0 650 -46 247 -91 388 -188 585 -54 112 -52 108 -127 220 -173 258 -450 516 "
	"-697 650 -27 14 -56 30 -64 35 -55 34 -255 113 -360 144 -380 109 -826 120 -1195 30 -142 -35 "
	"-186 -50 -329 -109 -153 -63 -310 -158 -516 -310 -181 -133 -195 -138 -345 -139 -154 -1 -162 3 "
	"-414 185 -70 51 -165 115 -181 122 -8 4 -28 16 -45 27 -40 25 -220 114 -272 134 -96 36 -120 44 "
	"-173 59 -179 51 -300 73 -480 87 -157 12 -198 11 -380 -5z m458 -861 c248 -60 351 -114 577 "
	"-304 192 -161 424 -274 635 -310 30 -5 82 -14 115 -19 192 -34 490 11 702 106 29 13 62 28 75 "
	"33 13 5 32 16 43 22 145 92 183 118 196 129 80 75 257 209 276 209 3 0 14 6 22 13 37 31 208 93 "
	"333 122 94 21 399 21 482 0 242 -62 388 -142 552 -301 70 -69 141 -154 181 -219 46 -74 129 "
	"-261 140 -315 2 -14 11 -45 18 -70 26 -90 38 -271 26 -382 -16 -134 -58 -304 -91 -366 -4 -9 "
	"-24 -49 -42 -88 -87 -181 -251 -364 -423 -471 -48 -30 -226 -113 -242 -113 -9 0 -35 -6 -58 -14 "
	"-22 -8 -78 -20 -125 -27 -218 -33 -454 -2 -655 86 -16 7 -37 16 -45 19 -41 18 -186 116 -240 "
	"164 -128 110 -301 226 -400 266 -25 10 -58 24 -75 31 -16 7 -55 20 -85 28 -187 53 -176 52 -405 "
	"52 -231 0 -277 -7 -430 -58 -119 -40 -143 -49 -195 -79 -8 -4 -24 -12 -35 -17 -11 -5 -37 -21 "
	"-58 -35 -21 -14 -41 -26 -45 -27 -4 0 -41 -27 -82 -60 -240 -190 -323 -248 -410 -283 -25 -10 "
	"-54 -23 -65 -29 -11 -6 -36 -14 -55 -18 -19 -4 -53 -12 -75 -18 -191 -49 -395 -47 -600 5 -68 "
	"18 -91 27 -190 75 -62 30 -151 83 -165 99 -3 3 -23 19 -45 35 -78 58 -206 200 -262 290 -42 68 "
	"-125 253 -139 310 -3 11 -11 43 -19 70 -57 209 -42 465 40 695 27 74 103 221 148 285 72 103 "
	"185 218 293 296 100 74 265 150 364 169 25 5 59 13 75 19 53 17 388 13 463 -5z",
)
PALETTE = {
	"paper": ("#FFFFFF", "#151517"),
	"canvas": ("#EFEFEF", "#09090A"),
	"ink": ("#0B0B0C", "#F4F4F5"),
	"muted": ("#8A8A8F", "#94949B"),
	"line": ("#E4E4E7", "#2A2A2F"),
	"card": ("#F3F3F4", "#1D1D21"),
	"accent": ("#E5322D", "#FF5A54"),
	# The wallpaper, in the same token the old dotted canvas used and at the same
	# strength. Both themes take their value from here, so the pattern needs no
	# colour-scheme rule of its own and cannot drift from the palette.
	"dots": ("#D1D1D4", "#26262B"),
	"success": ("#15803D", "#4ADE80"),
}


def data_script(fn: str, expose: tuple = ()) -> str:
	lines = [f'result = frappe.call("shop.storefront.page_data.{fn}")', "data.update(result)"]
	if expose:
		exposed = ", ".join(f'"{key}": result.get("{key}")' for key in expose)
		lines.append(f"data.page_data = {{{exposed}}}")
	return "\n".join(lines)


def generate():
	refs = upsert_variables(GROUP, PALETTE)
	styles = upsert_client_script("dot-styles", "CSS", theme_css(refs))
	register_components(refs)
	pages = [
		("dot-home", "Home", "home", home_blocks(refs), "home", (), False),
		("dot-products", "Products", "products", products_blocks(refs), "listing", (), False),
		("dot-product", "Product", "product/:slug", product_blocks(refs), "product_page", ("product",), False),
		("dot-collection", "Collection", "collection/:slug", collection_blocks(refs), "collection_page", (), False),
		("dot-cart", "Cart", "cart", cart_blocks(refs), "cart_page", ("cart",), False),
		("dot-checkout", "Checkout", "checkout", checkout_blocks(refs), "checkout_page", ("cart", "addresses", "address_cities", "address_provinces", "address_country", "landmark_required", "province_city_map", "cod_allowed_cities", "advance_instructions", "raast_instructions"), False),
		(
			"dot-order-confirmation",
			"Order Confirmed",
			"order-confirmation/:order_id",
			confirmation_blocks(refs),
			"order_confirmation",
			(),
			False,
		),
		("dot-account-orders", "Your Orders", "account/orders", account_blocks(refs), "account_orders", (), True),
		("dot-about", "About", "about", about_blocks(refs), "basic", (), False),
		("dot-contact", "Contact", "contact", contact_blocks(refs), "basic", (), False),
		("dot-faq", "FAQ", "faq", faq_blocks(refs), "basic", (), False),
	]
	for page_name, title, route, blocks, data_fn, expose, authenticated in pages:
		upsert_page(
			GROUP,
			page_name,
			title,
			route,
			blocks,
			data_script(data_fn, expose),
			client_scripts=[styles],
			authenticated_access=authenticated,
		)


def register_components(refs):
	"""Reusable pieces listed in Builder's insert panel; ids are namespaced so themes never overwrite each other."""
	for component_id, component_name, node in [
		("dot-navbar", "Dot Navbar", nav(refs)),
		("dot-footer", "Dot Footer", footer(refs)),
		("dot-cart-drawer", "Dot Cart Drawer", cart_drawer()),
		("dot-lightbox", "Dot Image Preview", lightbox()),
		("dot-hero", "Dot Hero", hero(refs)),
		("dot-product-card", "Dot Product Card", product_card(refs)),
		("dot-collection-tile", "Dot Collection Tile", collection_tile(refs)),
		("dot-filter-bar", "Dot Filter Bar", filter_bar(refs)),
		("dot-review-card", "Dot Review Card", review_card(refs)),
		("dot-delivery-card", "Dot Delivery Promise", delivery_card(refs)),
		("dot-trust-row", "Dot Spec Row", trust_row(refs)),
	]:
		upsert_component(component_id, component_name, node)


def theme_css(refs):
	return f"""
button {{ cursor: pointer; }}
button:disabled {{ opacity: 0.4; cursor: not-allowed; }}
:focus-visible {{ outline: 2px solid {refs["ink"]}; outline-offset: 3px; }}
input, textarea, select {{ font-family: {MONO}, monospace; }}
input::placeholder, textarea::placeholder {{ color: {refs["muted"]}; }}
input[type="radio"] {{ accent-color: {refs["ink"]}; }}
[data-shop="variant-option"][data-selected="true"] {{
	background: {refs["ink"]};
	color: {refs["paper"]};
	border-color: {refs["ink"]};
}}
[data-shop="cart-count"][data-empty="true"] {{ display: none; }}
[data-shop="filter-panel"][data-open="false"] {{ display: none; }}
[data-shop="filter-toggle"][aria-expanded="true"] {{
	background: {refs["ink"]};
	color: {refs["paper"]};
	border-color: {refs["ink"]};
}}
[data-shop="filter-toggle"][aria-expanded="true"] .filter-count {{
	background: {refs["paper"]};
	color: {refs["ink"]};
}}
a[data-active="true"] {{
	background: {refs["ink"]};
	color: {refs["paper"]};
	border-color: {refs["ink"]};
}}
[data-shop="rating-star"] {{ cursor: pointer; }}
[data-shop="rating-star"][data-selected="true"] {{ color: {refs["ink"]}; }}
[data-shop="thumb"][data-selected="true"] {{ border-color: {refs["ink"]}; }}
[data-shop="order-progress"] .progress-stage {{
	align-items: center;
	display: flex;
	flex: 1;
	flex-direction: column;
	gap: 9px;
	position: relative;
}}
[data-shop="order-progress"] .progress-stage::before {{
	background: {refs["line"]};
	content: "";
	height: 1px;
	position: absolute;
	right: 50%;
	top: 4px;
	width: 100%;
}}
[data-shop="order-progress"] .progress-stage:first-child::before {{ display: none; }}
[data-shop="order-progress"] .progress-stage[data-done="true"]::before {{ background: {refs["ink"]}; }}
.progress-stage .stage-dot {{
	background: {refs["paper"]};
	border: 1px solid {refs["line"]};
	border-radius: 50%;
	height: 9px;
	position: relative;
	width: 9px;
	z-index: 1;
}}
.progress-stage[data-done="true"] .stage-dot {{ background: {refs["ink"]}; border-color: {refs["ink"]}; }}
.progress-stage .stage-label {{
	color: {refs["muted"]};
	font-family: {MONO}, monospace;
	font-size: 10px;
	letter-spacing: 0.08em;
	text-align: center;
	text-transform: uppercase;
}}
.progress-stage[data-done="true"] .stage-label {{ color: {refs["ink"]}; }}
/* The confirmation page's info tiles share one two-column grid. A block
   hidden by a visibility condition is never rendered, so :nth-child counts
   only the tiles this order has — an odd count would otherwise strand the
   last one beside an empty cell. The grid collapses to one column on the
   phone, where there is no neighbour to fill. */
.order-tiles > *:last-child:nth-child(odd) {{ grid-column: span 2; }}
@media (max-width: 576px) {{
	.order-tiles > *:last-child:nth-child(odd) {{ grid-column: span 1; }}
}}
[data-shop="cart-drawer"] {{
	position: fixed;
	inset: 0;
	z-index: 90;
	pointer-events: none;
}}
[data-shop="cart-drawer"] .drawer-backdrop {{
	position: absolute;
	inset: 0;
	background: rgba(0, 0, 0, 0.45);
	display: none;
}}
[data-shop="cart-drawer"] .drawer-panel {{
	position: absolute;
	top: 0;
	right: 0;
	height: 100%;
	width: min(420px, 100vw);
	background: {refs["paper"]};
	color: {refs["ink"]};
	display: none;
	flex-direction: column;
}}
[data-shop="cart-drawer"][data-open="true"] {{ pointer-events: auto; }}
[data-shop="cart-drawer"][data-open="true"] .drawer-backdrop {{ display: block; }}
[data-shop="cart-drawer"][data-open="true"] .drawer-panel {{ display: flex; }}
.drawer-header {{
	align-items: center;
	border-bottom: 1px solid {refs["line"]};
	display: flex;
	flex-shrink: 0;
	justify-content: space-between;
	padding: 20px 24px;
}}
.drawer-title {{
	font-family: {MONO}, monospace;
	font-size: 12px;
	letter-spacing: 0.12em;
	text-transform: uppercase;
}}
.drawer-close {{
	background: none;
	border: 0;
	color: {refs["ink"]};
	font-size: 20px;
	line-height: 1;
	padding: 2px 6px;
}}
.drawer-items {{ flex: 1; overflow-y: auto; padding: 4px 24px; }}
.drawer-item {{
	align-items: flex-start;
	border-bottom: 1px solid {refs["line"]};
	display: flex;
	gap: 14px;
	padding: 18px 0;
}}
.drawer-item:last-child {{ border-bottom: 0; }}
.drawer-thumb {{
	background: {refs["card"]};
	border-radius: 10px;
	flex-shrink: 0;
	height: 64px;
	object-fit: cover;
	width: 64px;
}}
.drawer-info {{ display: flex; flex: 1; flex-direction: column; gap: 4px; min-width: 0; }}
.drawer-name {{
	color: {refs["ink"]};
	font-size: 13px;
	font-weight: 500;
	line-height: 1.45;
	text-decoration: none;
}}
.drawer-rate {{
	color: {refs["muted"]};
	font-family: {MONO}, monospace;
	font-size: 11px;
	letter-spacing: 0.04em;
}}
.drawer-qty {{ align-items: center; display: flex; gap: 8px; margin-top: 8px; }}
.drawer-qty > button {{
	align-items: center;
	background: {refs["paper"]};
	border: 1px solid {refs["line"]};
	border-radius: 999px;
	color: {refs["ink"]};
	display: flex;
	font-size: 13px;
	height: 26px;
	justify-content: center;
	width: 26px;
}}
.drawer-qty > span {{
	font-family: {MONO}, monospace;
	font-size: 12px;
	min-width: 16px;
	text-align: center;
}}
.drawer-qty > .drawer-remove {{
	background: none;
	border: 0;
	color: {refs["muted"]};
	font-family: {MONO}, monospace;
	font-size: 10px;
	height: auto;
	letter-spacing: 0.1em;
	margin-left: 8px;
	padding: 0;
	text-transform: uppercase;
	width: auto;
}}
.drawer-amount {{
	flex-shrink: 0;
	font-family: {MONO}, monospace;
	font-size: 12px;
	font-weight: 500;
}}
.drawer-empty {{
	color: {refs["muted"]};
	font-family: {MONO}, monospace;
	font-size: 12px;
	letter-spacing: 0.08em;
	padding: 48px 0;
	text-align: center;
	text-transform: uppercase;
}}
.drawer-footer {{
	border-top: 1px solid {refs["line"]};
	display: flex;
	flex-direction: column;
	flex-shrink: 0;
	gap: 12px;
	padding: 18px 24px 22px;
}}
.drawer-total-row {{
	align-items: baseline;
	display: flex;
	font-family: {MONO}, monospace;
	font-size: 13px;
	justify-content: space-between;
	letter-spacing: 0.06em;
	text-transform: uppercase;
}}
.drawer-note {{
	color: {refs["muted"]};
	font-size: 11px;
	line-height: 1.5;
	margin-top: -6px;
}}
.drawer-actions {{ display: grid; gap: 10px; grid-template-columns: 1fr 1fr; }}
.drawer-view, .drawer-checkout {{
	border-radius: 999px;
	font-family: {MONO}, monospace;
	font-size: 11px;
	letter-spacing: 0.12em;
	padding: 13px 16px;
	text-align: center;
	text-decoration: none;
	text-transform: uppercase;
}}
.drawer-view {{
	border: 1px solid {refs["ink"]};
	color: {refs["ink"]};
}}
.drawer-checkout {{
	background: {refs["ink"]};
	border: 1px solid {refs["ink"]};
	color: {refs["paper"]};
}}
/* Image preview. Sits above the cart drawer (z 90) and the buy bar (z 80) so a
   customer who is part-way down a product page still gets the preview over the
   bar, not behind it. Hidden with pointer-events rather than display so the
   open/close is a single attribute flip, like the drawer above. */
[data-shop="lightbox"] {{
	position: fixed;
	inset: 0;
	z-index: 120;
	pointer-events: none;
}}
[data-shop="lightbox"] .lightbox-backdrop {{
	position: absolute;
	inset: 0;
	background: rgba(9, 9, 10, 0.94);
	display: none;
}}
[data-shop="lightbox"][data-open="true"] {{ pointer-events: auto; }}
[data-shop="lightbox"][data-open="true"] .lightbox-backdrop {{ display: block; }}
/* touch-action:none is what makes the pinch ours: without it the browser claims
   the two-finger gesture for its own page zoom and the image never moves. */
.lightbox-stage {{
	position: absolute;
	inset: 0;
	align-items: center;
	cursor: grab;
	display: none;
	justify-content: center;
	overflow: hidden;
	touch-action: none;
}}
[data-shop="lightbox"][data-open="true"] .lightbox-stage {{ display: flex; }}
.lightbox-stage[data-panning="true"] {{ cursor: grabbing; }}
.lightbox-image {{
	max-height: 82%;
	max-width: 92%;
	/* The transform carries both zoom and pan, so the browser has to keep it on
	   the compositor or every pointermove re-rasterises the photo. */
	object-fit: contain;
	transform-origin: center center;
	user-select: none;
	-webkit-user-drag: none;
	will-change: transform;
}}
.lightbox-close {{
	/* Same surface as the zoom bar: white pill, dark glyph. It was a translucent
	   white disc carrying a white ×, which put it in a different visual language
	   from the one control sitting in the same overlay - and a white glyph on 10%
	   white over a dark backdrop is thin in both schemes. #0B0B0C on #FFFFFF is
	   19.67:1. Fixed colours for the same reason the bar uses them: the overlay
	   pins its own appearance, and the page's light-dark() palette would invert
	   under it. */
	background: rgba(255, 255, 255, 0.96);
	border: 0;
	border-radius: 999px;
	color: #0B0B0C;
	cursor: pointer;
	/* Gated on data-open like the backdrop, stage and bar. Without this the ×
	   paints over the product page at all times: the overlay root only sets
	   pointer-events:none while closed, which stops the button being clickable
	   but not being drawn. */
	display: none;
	font-size: 22px;
	line-height: 1;
	padding: 11px 15px;
	position: absolute;
	right: 18px;
	top: 18px;
	z-index: 2;
}}
[data-shop="lightbox"][data-open="true"] .lightbox-close {{ display: block; }}
/* The bar and its contents take fixed colours rather than theme variables, and
   that is deliberate. The overlay already fixes its own appearance: a dark
   backdrop and a white pill, in both colour schemes. Feeding it the page's
   light-dark() palette means the same rules invert under it in dark mode, and
   `ink` becomes #F4F4F5 - so the zoom readout and the slider thumb render
   #F4F4F5 on a #FFFFFF bar, 1.1:1, i.e. invisible. The variables describe the
   page behind the overlay; this is a surface of its own.
   Ratios below are against the #FFFFFF bar. */
.lightbox-bar {{
	align-items: center;
	background: rgba(255, 255, 255, 0.96);
	border-radius: 999px;
	bottom: 26px;
	display: none;
	gap: 14px;
	left: 50%;
	padding: 11px 18px;
	position: absolute;
	transform: translateX(-50%);
	/* visibility is discrete: transitioned plainly it holds at `visible` for the
	   whole fade, leaving an invisible-but-tappable bar under the fingers. Zeroed
	   on the way out, and delayed to the end of the fade on the way back. */
	transition: opacity 150ms ease, visibility 0s linear 150ms;
	z-index: 2;
}}
[data-shop="lightbox"][data-open="true"] .lightbox-bar {{ display: flex; }}
/* The slider is on the phone too, but a pinch is a two-finger gesture and the bar
   sits right under the fingers. It steps aside for the duration of the pinch and
   comes straight back when the fingers lift. */
[data-shop="lightbox"][data-pinching="true"] .lightbox-bar {{
	opacity: 0;
	visibility: hidden;
	transition: opacity 150ms ease, visibility 0s linear 0s;
}}
.lightbox-label {{
	/* 5.06:1. The theme's muted is #8A8A8F, which is only 3.44:1 and short of AA
	   for text this small. */
	color: #6E6E75;
	font-family: {MONO}, monospace;
	font-size: 10px;
	letter-spacing: 0.1em;
	text-transform: uppercase;
}}
.lightbox-level {{ color: #0B0B0C; min-width: 42px; text-align: right; }}
.lightbox-zoom {{
	-webkit-appearance: none;
	appearance: none;
	background: #BDBDC4;
	border-radius: 999px;
	height: 4px;
	width: 170px;
}}
.lightbox-zoom::-webkit-slider-thumb {{
	-webkit-appearance: none;
	appearance: none;
	background: #0B0B0C;
	border: 0;
	border-radius: 50%;
	box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
	cursor: pointer;
	height: 18px;
	width: 18px;
}}
.lightbox-zoom::-moz-range-thumb {{
	background: #0B0B0C;
	border: 0;
	border-radius: 50%;
	box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
	cursor: pointer;
	height: 18px;
	width: 18px;
}}
@media (prefers-reduced-motion: reduce) {{
	.lightbox-bar {{ transition: none; }}
	/* With no fade, visibility has to flip with the attribute, not after a delay
	   that is no longer being waited out. */
	[data-shop="lightbox"][data-pinching="true"] .lightbox-bar {{
		visibility: hidden;
		transition: none;
	}}
}}
.pdp-buybar {{
	bottom: 18px;
	display: flex;
	justify-content: center;
	left: 0;
	padding: 0 20px;
	position: fixed;
	right: 0;
	z-index: 80;
}}
.pdp-buybar[data-visible="false"] {{ display: none; }}
.pdp-buybar-inner {{
	align-items: center;
	background: {refs["paper"]};
	border: 1px solid {refs["line"]};
	border-radius: 999px;
	display: flex;
	gap: 20px;
	justify-content: space-between;
	padding: 10px 10px 10px 24px;
	width: fit-content;
}}
@media (max-width: 640px) {{
	.pdp-buybar {{ bottom: 0; padding: 0 12px 10px; }}
	.pdp-buybar-inner {{ width: 100%; }}
	[data-shop="qty-inc"], [data-shop="qty-dec"], [data-drawer-step] {{ min-height: 36px; min-width: 36px; }}
	.drawer-close {{ padding: 10px; margin: -10px; }}
	[data-shop="remove"], .drawer-remove {{ padding: 8px 6px; }}
}}
/* The hero's product carousel.

   Structure and behaviour from a CodePen coverflow
   (codepen.io/frise/pen/mZvKpe): items sit absolutely in a list, and a
   data-pos of -2..2 drives the transform, so moving one only has to rewrite a
   few attributes.

   Two deliberate departures. The pen's items are 150x250 gradient tiles with a
   fixed size; these are the theme's own product cards, which carry a photo, a
   condition tag, a name and a price - so the card here is the photo and the
   name and nothing else. And the tags are the builder's, not the pen's
   <ul>/<li>: the cards come out of the theme's repeater as <a>, so the list is
   a div and the items are its children. The mechanism is the pen's; the markup
   is not. */
.carousel__list {{
	box-sizing: border-box;
	display: flex;
	/* The cards are absolutely positioned, so nothing gives the list a height.
		This one is the card's whole height - a 250px photo, the 12px gap and the
		38px name - divided by the 91% the cards are laid out at, so that the
		centre card's 1.1 scale lands back on exactly this. */
	height: 330px;
	justify-content: center;
	list-style: none;
	perspective: 300px;
	position: relative;
	width: 100%;
}}
.carousel__list > a {{
	box-sizing: border-box;
	color: inherit;
	/* 91% rather than 100%: the centre card is scaled up 10% and 1/1.1 is
	   90.9%, so after the scale it fills the list exactly instead of hanging 15px
	   over the top and bottom of it, where the showcase's overflow would cut the
	   picture off. Every card is laid out at this size and then scaled by its
	   position, so the sizes stay in proportion. */
	height: 91%;
	position: absolute;
	text-decoration: none;
	transition: transform 0.3s ease-in, opacity 0.3s ease-in, filter 0.3s ease-in;
	width: 190px;
}}
/* The photo is a fixed height in pixels, not a share of what is left.
   Left as flex:1 it took whatever the name did not use, and the name is one or
   two lines depending on the product - so a short name gave its photograph 242px
   and a long one 223px, and five cards in the same row held five differently
   sized pictures. The photos in this catalogue are not all the same shape either,
   so nothing about the picture itself would have equalised them: object-fit:cover
   fills whatever box it is given, and the box was the thing that varied. */
.carousel__list > a > div:first-child {{
	aspect-ratio: auto;
	flex: 0 0 auto;
	height: 250px;
	min-height: 0;
}}
/* Photo and name only. The condition tag, the stars and the price are still in
   the card, just not drawn - the carousel is a browse, not a price list. */
.carousel__list > a > *:not(:first-child):not(h3) {{
	display: none;
}}
/* Two lines' worth, fixed, so a one-line name reserves the same room a two-line
   one does. Without this the name would still be the variable that decides how
   tall the card is. */
.carousel__list > a h3 {{
	-webkit-box-orient: vertical;
	-webkit-line-clamp: 2;
	flex: 0 0 auto;
	height: 38px;
	overflow: hidden;
	transition: opacity 0.3s ease-in;
}}
/* Only the centre card is named.
   A card at the side is 171px wide and sits 76px off centre, so its name runs
   out from under the centre card on both sides and the two names land on top of
   each other - three products' names stacked into one unreadable block. The
   photo alone is enough to recognise it by; the name belongs to the card being
   looked at. */
.carousel__list > a:not([data-pos="0"]) h3 {{
	opacity: 0;
}}
/* The pen's positions, unchanged. A card at the side is scaled back, dimmed and
   blurred; the centre one is on top and sharp. */
/* The card being looked at is a tenth bigger than the ones beside it. */
.carousel__list > a[data-pos="0"] {{
	transform: scale(1.1);
	z-index: 5;
}}
.carousel__list > a[data-pos="-1"],
.carousel__list > a[data-pos="1"] {{
	filter: blur(1px) grayscale(10%);
	opacity: 0.7;
	z-index: 4;
}}
.carousel__list > a[data-pos="-1"] {{
	transform: translateX(-40%) scale(0.9);
}}
.carousel__list > a[data-pos="1"] {{
	transform: translateX(40%) scale(0.9);
}}
/* The hero headline on a phone.

   "Collected properly." is 8.57em wide at this typeface - measured, not
   estimated - so a fixed 36px needs 308px of column and wraps below a 372px
   viewport. 390px was fine, 360px and 320px were not, and those are the widths
   most of the shop's customers are actually on.

   So it is sized against the viewport instead of picked once. 9vw is the
   coefficient that fits at 320px, where the column is 260px and the text needs
   to be under 30px. The cap is 44px, not 36px: this covers the whole stacked
   range, which starts at 1024px and not at 576px, and a tablet has room for
   more than a phone. Above 1024px the hero is two columns and the copy has
   540px to itself, which 62px fits into. The floor is only reached below about
   300px, where nothing else on the page is legible either. */
@media only screen and (max-width: 1023px) {{
	.hero__title {{
		font-size: clamp(27px, 9vw, 44px);
	}}
}}
/* Only three cards are ever on show: the one being looked at and the two
   either side of it. The pen has a third tier at 40% opacity, blurred 3px and
   pushed out to 70%, and in a box this size that tier read as a hard vertical
   edge of clipped card at each end rather than a sense of depth. It is parked
   instead of drawn.

   Parked, not dropped: all five products are still in the rotation and still
   come round, they are just never on show at the same time. Positions wrap the
   short way round, so the two cards either side of the centre are always the
   ones drawn and the row never ends up with a gap on one side. Off the edge, and
   untappable, so a hidden card cannot be clicked on the way past. */
.carousel__list > a[data-pos="-2"],
.carousel__list > a[data-pos="2"],
.carousel__list > a[data-pos="-3"],
.carousel__list > a[data-pos="3"] {{
	opacity: 0;
	pointer-events: none;
}}
.carousel__list > a[data-pos="-2"],
.carousel__list > a[data-pos="-3"] {{
	transform: translateX(-110%) scale(0.7);
}}
.carousel__list > a[data-pos="2"],
.carousel__list > a[data-pos="3"] {{
	transform: translateX(110%) scale(0.7);
}}
/* Not yet placed. Before the script runs every card would sit at the centre on
   top of the others, which is the one state worth never showing. */
.carousel__list:not([data-ready]) > a {{
	opacity: 0;
}}
/* While the cards are sliding, a click would land on whichever card happens to
   be passing under the finger. */
.carousel__list[data-moving="true"] > a {{
	pointer-events: none;
}}
@media only screen and (max-width: 1023px) {{
	.carousel__list {{ height: 297px; }}
	.carousel__list > a {{ width: 170px; }}
	.carousel__list > a > div:first-child {{ height: 220px; }}
}}
@media only screen and (max-width: 576px) {{
	.carousel__list {{ height: 275px; }}
	.carousel__list > a {{ width: 152px; }}
	.carousel__list > a > div:first-child {{ height: 200px; }}
}}
/* The pen's 0.3s slide is exactly the kind of motion this has to drop. The
   positions still change, they just arrive at once. */
@media (prefers-reduced-motion: reduce) {{
	.carousel__list > a {{ transition: none; }}
}}
#reviews {{ scroll-margin-top: 100px; }}
"""


def mono(size="12px", weight="400", color=None, spacing="0.1em", upper=True) -> dict:
	styles = {
		"fontFamily": MONO,
		"fontSize": size,
		"fontWeight": weight,
		"height": "fit-content",
		"letterSpacing": spacing,
		"width": "fit-content",
	}
	if color:
		styles["color"] = color
	if upper:
		styles["textTransform"] = "uppercase"
	return styles


def label(refs, text, color=None, size="11px", element="p", **extra):
	return block(element, text=text, styles=mono(size=size, color=color or refs["muted"], spacing="0.14em"), **extra)


def display(refs, text, size="34px", mobile_size="26px", element="h2", weight="500"):
	return block(
		element,
		text=text,
		styles={
			"color": refs["ink"],
			"fontFamily": HEAD,
			"fontSize": size,
			"fontWeight": weight,
			"height": "fit-content",
			"letterSpacing": "-0.02em",
			"lineHeight": "1.1",
			"width": "fit-content",
		},
		mobile={"fontSize": mobile_size},
	)


def prose(refs, text, size="14px", color=None, width="100%"):
	return block(
		"p",
		text=text,
		styles={
			"color": color or refs["muted"],
			"fontSize": size,
			"height": "fit-content",
			"lineHeight": "1.65",
			"width": width,
		},
	)


def run(refs, parts, size="12px", color=None, weight="400", family=None):
	"""Row of spans with no gap so bound values sit inside literal text."""
	spans = []
	for bound, value in parts:
		styles = {
			"color": color or refs["muted"],
			"fontSize": size,
			"fontWeight": weight,
			"height": "fit-content",
			"whiteSpace": "pre",
			"width": "fit-content",
		}
		if family:
			styles["fontFamily"] = family
			styles["letterSpacing"] = "0.06em"
		spans.append(
			block(
				"span",
				text="" if bound else value,
				styles=styles,
				dynamicValues=[dv(value, "innerHTML")] if bound else [],
			)
		)
	return block(
		"div",
		styles={"alignItems": "baseline", "display": "flex", "flexDirection": "row", "width": "fit-content"},
		children=spans,
	)


def pill(refs, text, href=None, variant="solid", full=False, attrs=None, **extra):
	element = "a" if href else "button"
	base_attrs = {"href": href} if href else {"type": "button"}
	base_attrs.update(attrs or {})
	styles = {
		"backgroundColor": refs["ink"] if variant == "solid" else "transparent",
		"borderColor": refs["ink"] if variant != "quiet" else refs["line"],
		"borderRadius": "999px",
		"borderStyle": "solid",
		"borderWidth": "1px",
		"color": refs["paper"] if variant == "solid" else refs["ink"],
		"fontFamily": MONO,
		"fontSize": "11px",
		"height": "fit-content",
		"letterSpacing": "0.14em",
		"padding": "14px 28px",
		"textAlign": "center",
		"textDecoration": "none",
		"textTransform": "uppercase",
		"width": "100%" if full else "fit-content",
	}
	return block(element, text=text, attrs=base_attrs, styles=styles, **extra)


def directions_button(refs, key):
	"""Full-width pill link that opens directions to a pickup location.

	Replaces the old text link; ``key`` is the dataScript path to the
	directions URL (checkout uses the bare key, confirmation the nested one).

	Builder's reset.css forces ``.__text_block__ a { color: var(--link-color);
	text-decoration: underline; background-color: transparent }`` on every
	anchor inside a text block, and that selector (0,1,1) beats this block's
	own class (0,1,0) — clobbering the pill's look. Declaring the three
	properties ``!important`` wins outright; ``sanitize_style_value`` passes
	``!important`` through untouched."""
	return block(
		"a",
		text="Get directions",
		attrs={"target": "_blank", "rel": "noopener"},
		styles={
			"backgroundColor": f"{refs['ink']} !important",
			"borderColor": refs["ink"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"boxSizing": "border-box",
			"color": f"{refs['paper']} !important",
			"fontFamily": MONO,
			"fontSize": "10px",
			"height": "fit-content",
			"letterSpacing": "0.12em",
			"padding": "11px 20px",
			"textAlign": "center",
			"textDecoration": "none !important",
			"textTransform": "uppercase",
			"width": "100%",
		},
		dynamicValues=[dv(key, "href", "attribute")],
		visibilityCondition={"key": key, "comesFrom": "dataScript"},
	)


def contact_buttons(refs, dial_key, wa_key, phone_key):
	"""Two separate pill buttons replacing the plain phone line: the number
	itself (tap to dial on mobile; desktop JS turns it into copy-to-clipboard
	with a brief "Copied ✓" pop — storefront.js keys off data-shop=
	"phone-copy") and, beside it with a gap, a WhatsApp chat button (wa.me).
	Matches the directions pill's look; reset.css's link clobber is beaten
	with ``!important`` exactly as ``directions_button`` does. ``*_key`` are
	dataScript paths (bare on checkout, nested on confirmation)."""
	half = {
		**mono(size="10px", color=refs["paper"], spacing="0.12em"),
		"backgroundColor": f"{refs['ink']} !important",
		"borderColor": refs["ink"],
		"borderRadius": "999px",
		"borderStyle": "solid",
		"borderWidth": "1px",
		"boxSizing": "border-box",
		"color": f"{refs['paper']} !important",
		"flex": "1 1 50%",
		"minWidth": "0",
		"padding": "11px 8px",
		"textAlign": "center",
		"textDecoration": "none !important",
	}
	return block(
		"div",
		styles={
			"alignItems": "stretch",
			"display": "flex",
			"gap": "8px",
			"width": "100%",
		},
		children=[
			block(
				"a",
				text="",
				attrs={"data-shop": "phone-copy"},
				styles=half,
				dynamicValues=[
					dv(phone_key, "innerHTML"),
					dv(dial_key, "href", "attribute"),
				],
			),
			block(
				"a",
				text="WhatsApp",
				attrs={"target": "_blank", "rel": "noopener"},
				styles=half,
				dynamicValues=[dv(wa_key, "href", "attribute")],
				visibilityCondition={"key": wa_key, "comesFrom": "dataScript"},
			),
		],
		visibilityCondition={"key": phone_key, "comesFrom": "dataScript"},
	)


def map_frame(refs, key, height="170px", margin="2px"):
	"""View-only map embed with our own zoom controls.

	The iframe ignores pointer events, so gestures inside it can never pan
	away from the pin (nor launch the maps app). The buttons rewrite the
	embed URL symmetrically around the pin — OSM's bbox is rebuilt centred
	on the marker, Google's ``z=`` moves with a fixed ``q=`` centre — so the
	location is exactly centred at every zoom level. ``key`` is the
	dataScript path to the map URL (bare on checkout, nested on confirmation)."""
	zoom_styles = {
		"alignItems": "center",
		"backgroundColor": refs["paper"],
		"borderColor": refs["line"],
		"borderRadius": "4px",
		"borderStyle": "solid",
		"borderWidth": "1px",
		"color": refs["ink"],
		"cursor": "pointer",
		"display": "flex",
		"fontFamily": MONO,
		"fontSize": "13px",
		"fontWeight": "600",
		"height": "26px",
		"justifyContent": "center",
		"lineHeight": "1",
		"padding": "0",
		"width": "26px",
	}

	def zoom_button(symbol, direction, label):
		# type=button: the checkout map renders inside the form. Interactive
		# content inside a label doesn't toggle that label's radio either, so
		# zooming never changes the selected location.
		return block(
			"button",
			text=symbol,
			attrs={"aria-label": label, "data-shop": "map-zoom", "data-delta": str(direction), "type": "button"},
			styles=dict(zoom_styles),
		)

	return block(
		"div",
		attrs={"data-shop": "map-frame"},
		styles={
			"borderRadius": "4px",
			"height": height,
			"marginTop": margin,
			"position": "relative",
			"width": "100%",
		},
		visibilityCondition={"key": key, "comesFrom": "dataScript"},
		children=[
			block(
				"iframe",
				attrs={
					"loading": "lazy",
					"referrerpolicy": "no-referrer-when-downgrade",
					"title": "Pickup location map",
				},
				styles={
					"border": "0",
					"borderRadius": "4px",
					"display": "block",
					"height": "100%",
					"pointerEvents": "none",
					"width": "100%",
				},
				dynamicValues=[dv(key, "src", "attribute")],
			),
			block(
				"div",
				styles={
					"display": "flex",
					"flexDirection": "column",
					"gap": "4px",
					"position": "absolute",
					"right": "8px",
					"top": "8px",
					"zIndex": "1",
				},
				children=[
					zoom_button("+", 1, "Zoom in"),
					zoom_button("-", -1, "Zoom out"),
				],
			),
		],
	)


def panel(refs, children, styles=None, mobile=None, name=None, tone="paper"):
	base = {
		"backgroundColor": refs[tone],
		"borderRadius": "20px",
		"display": "flex",
		"flexDirection": "column",
		"flexShrink": 0,
		"gap": "24px",
		"padding": "40px",
		"width": "100%",
	}
	base.update(styles or {})
	responsive = {"borderRadius": "16px", "gap": "20px", "padding": "24px 18px"}
	responsive.update(mobile or {})
	return block("div", name=name, styles=base, mobile=responsive, children=children)


def stack(children, name=None):
	return block(
		"div",
		name=name or "Stack",
		styles={
			"display": "flex",
			"flexDirection": "column",
			"flexShrink": 0,
			"gap": "16px",
			"maxWidth": "1040px",
			"padding": "0 20px",
			"width": "100%",
		},
		mobile={"gap": "12px", "padding": "0 12px"},
		children=children,
	)


def section_head(refs, index, title, link_label=None, link_href=None):
	left = block(
		"div",
		styles={"display": "flex", "flexDirection": "column", "gap": "10px", "width": "fit-content"},
		children=[label(refs, index), display(refs, title, size="24px", mobile_size="20px")],
	)
	children = [left]
	if link_label:
		children.append(
			block(
				"a",
				text=link_label,
				attrs={"href": link_href},
				styles={**mono(size="11px", color=refs["muted"], spacing="0.14em"), "textDecoration": "none"},
			)
		)
	return block(
		"div",
		name="Section Head",
		styles={
			"alignItems": "flex-end",
			"display": "flex",
			"flexDirection": "row",
			"justifyContent": "space-between",
			"width": "100%",
		},
		children=children,
	)


def spec_strip(refs, items, tone=None):
	entry = lambda text: block(
		"p",
		text=text,
		styles=mono(size="10px", color=tone or refs["muted"], spacing="0.16em"),
	)
	return block(
		"div",
		name="Spec Strip",
		styles={
			"borderTopColor": refs["line"],
			"borderTopStyle": "solid",
			"borderTopWidth": "1px",
			"display": "flex",
			"flexDirection": "row",
			"flexWrap": "wrap",
			"gap": "10px 28px",
			"paddingTop": "18px",
			"width": "100%",
		},
		children=[entry(text) for text in items],
	)


def utility_row(refs, text, href, glyph="→"):
	color = refs["ink"]
	return block(
		"a",
		name="Utility Row",
		attrs={"href": href},
		styles={
			"alignItems": "center",
			"borderColor": refs["line"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"color": color,
			"display": "flex",
			"flexDirection": "row",
			"justifyContent": "space-between",
			"padding": "13px 20px",
			"textDecoration": "none",
			"width": "100%",
		},
		children=[
			block("span", text=text, styles=mono(size="11px", color=color, spacing="0.14em")),
			block("span", text=glyph, styles=mono(size="12px", color=refs["muted"], spacing="0")),
		],
	)


# The wallpaper that backs every page: the monogram repeated on a checkerboard, so
# the ARRANGEMENT is the diamond -- four monograms leave a four-edged void between
# them, with a mark at each of its corners. The pitches are flush, so there is no
# gutter between neighbours, and the tile is a whole multiple of both, which puts a
# monogram centred on each seam: half in one tile, half in the next, its two halves
# meeting across the repeat as an infinity.
#
# Painted through a CSS mask, and that is what makes it adaptive. A mask reads only
# shape coverage, so the mark's own fill is irrelevant and the visible colour comes
# from this element's background-color -- which is refs["dots"], the same token the
# old dotted canvas used. Neither the SVG nor this file needs a colour-scheme rule
# of its own.
WALLPAPER_URL = "/assets/shop/img/wallpaper-7.svg"
# These must equal the SVG's own width/height to the digit, and the reason is
# sharper than "so it looks right": the SVG declares preserveAspectRatio="none",
# and its viewBox is the same two numbers, so nothing can be refitted or
# re-centred. Get them out of step and the browser scales the tile to fit, the
# artwork pulls away from the edge, and the repeat shows a gap on one side and a
# doubled hairline on the other. That is one bug, not two, and it reads as
# "monograms overlap in places" plus "the right edge has a gap".
#
# A two-value size because the tile is NOT square: the mark is 0.866 as wide as it
# is tall, so equal clear space on both axes needs two different pitches.
# 149.2746 x 160.0000 is 2 rows, authored as a 40px mark with a 40px gap -- the gap being
# one monogram's own length, which is what the pattern was tuned to.
WALLPAPER_TILE = "149.2746px 160.0000px"
# Same tile at 70%, so the marks land near 28px instead of 40px. Scaling the tile
# keeps the gap proportional to the mark, which a separately authored asset at a
# different size would not.
WALLPAPER_TILE_MOBILE = "104.492px 112px"


def wallpaper(refs):
	return block(
		"div",
		name="Wallpaper",
		attrs={"aria-hidden": "true"},
		styles={
			"WebkitMask": f'url("{WALLPAPER_URL}") repeat',
			"mask": f'url("{WALLPAPER_URL}") repeat',
			"WebkitMaskSize": WALLPAPER_TILE,
			"maskSize": WALLPAPER_TILE,
			"backgroundColor": refs["dots"],
			"inset": "0",
			"pointerEvents": "none",
			"position": "absolute",
			# -1, not 0. A positioned element with z-index 0 paints in a later
			# step than plain in-flow blocks, so at 0 this layer sat ON TOP of the
			# New arrival and Collections cards and made them look translucent.
			# That only happens because the root below is a stacking context; if
			# the root ever loses its z-index, -1 would fall behind the canvas.
			"zIndex": "-1",
		},
		mobile={
			"WebkitMaskSize": WALLPAPER_TILE_MOBILE,
			"maskSize": WALLPAPER_TILE_MOBILE,
		},
	)


# Where the scrim reaches full opacity, measured up from the bottom of the page.
# This has to clear the footer, because the footer is what the scrim exists for:
# 48px of footer bottom padding + 149px of footer content on a desktop, and
# 36px + 241px on a phone, where the link columns stack. Getting this wrong in the
# lenient direction leaves the pattern half-visible behind the links; getting it
# wrong the other way paints a flat band over the last product card.
WALLPAPER_SCRIM_ONSET = "206px"
WALLPAPER_SCRIM_ONSET_MOBILE = "288px"
# How far above that the scrim fades in from nothing. Long enough to be a fade
# rather than a step, short enough that the pattern is still plainly present over
# the products themselves.
WALLPAPER_SCRIM_RAMP = "340px"
WALLPAPER_SCRIM_RAMP_MOBILE = "320px"


def _scrim_mask(onset, ramp):
	"""Three stops, not two: the ramp ENDS above the footer and stays put below it.

	A single `transparent -> #000` ramp over the whole distance looks right on
	inspection and is wrong in use -- it only ever reaches about half opacity where
	the text actually starts, which leaves the pattern plainly visible behind the
	links while looking fine at the bottom of the page. So: nothing above, fully
	opaque from `onset` down, and flat to the end.
	"""
	return (
		f"linear-gradient(to bottom, "
		f"transparent calc(100% - {int(onset[:-2]) + int(ramp[:-2])}px), "
		f"#000 calc(100% - {onset}), #000 100%)"
	)


def wallpaper_scrim(refs):
	"""Ramps the wallpaper out under the footer, so the footer text has clean canvas.

	Why the footer needs this at all: it is the only part of the page that puts
	10-13px body text straight onto the pattern. The cards are opaque panels and
	sit on their own surface; the footer deliberately does not, "so it stays out of
	the way". That was fine against a 24px grid of 1px dots. Against 40px solid
	monograms it is not, and it only showed up in light mode -- there the marks are
	dark on light, the same polarity as the text, so at small sizes they merge. In
	dark mode the text sits ~8x further from the canvas than the marks do and wins
	comfortably. The wallpaper's contrast against the canvas is in fact identical in
	both themes (1.33 / 1.32), so this is about polarity and size, not loudness.

	A separate layer in the canvas colour, rather than compositing a gradient into
	the wallpaper's own mask. mask-composite would need `intersect` for every engine
	plus the legacy `-webkit-mask-composite: source-in`, whose layer-order semantics
	are not the same as the standard property's -- a reliable way to ship a fade
	that silently fails in half the browsers. This needs no compositing at all.

	It must come AFTER wallpaper() in the children: both sit at z-index -1, and
	among elements sharing a z-index the later one paints on top.
	"""
	return block(
		"div",
		name="Wallpaper Scrim",
		attrs={"aria-hidden": "true"},
		styles={
			"WebkitMask": _scrim_mask(WALLPAPER_SCRIM_ONSET, WALLPAPER_SCRIM_RAMP),
			"mask": _scrim_mask(WALLPAPER_SCRIM_ONSET, WALLPAPER_SCRIM_RAMP),
			"backgroundColor": refs["canvas"],
			"inset": "0",
			"pointerEvents": "none",
			"position": "absolute",
			# A pair with the -1 in wallpaper() above -- same reason, same caveat.
			"zIndex": "-1",
		},
		mobile={
			"WebkitMask": _scrim_mask(WALLPAPER_SCRIM_ONSET_MOBILE, WALLPAPER_SCRIM_RAMP_MOBILE),
			"mask": _scrim_mask(WALLPAPER_SCRIM_ONSET_MOBILE, WALLPAPER_SCRIM_RAMP_MOBILE),
		},
	)


def shell(refs, children):
	node = root(
		{
			"alignItems": "center",
			"backgroundColor": refs["canvas"],
			"color": refs["ink"],
			"position": "relative",
			# With position:relative alone this is not a stacking context, so the
			# wallpaper's z-index:-1 would escape it and paint behind the canvas.
			# These two lines are a pair with wallpaper() above.
			"zIndex": "0",
			"display": "flex",
			"flexDirection": "column",
			"flexShrink": 0,
			"fontFamily": HEAD,
			"gap": "16px",
			"minHeight": "100vh",
			"paddingTop": "94px",
			"width": "100%",
		},
		# Order matters between the first two: both sit at z-index -1, and among
		# elements sharing a z-index the later one paints on top, so the scrim has
		# to come after the wallpaper it is there to fade out.
		[wallpaper(refs), wallpaper_scrim(refs)] + children + [component_ref("dot-cart-drawer")],
	)
	node["mobileStyles"] = {"gap": "12px", "paddingTop": "78px"}
	return [node]


def brand_glyph(refs):
	"""The small accent monogram that sits where the dot used to.

	Tinted with ``refs["accent"]`` and dropped below full opacity so it reads as a
	second mark rather than competing with the wordmark. The accent variable is a
	light-dark() pair in /builder_assets/variables.css, so it follows the OS in
	both directions rather than being pinned to the light red here.

	Both the viewBox and the group transform are required: the paths carry
	coordinates in the thousands and the transform is what maps them into the
	viewBox.
	"""
	return block(
		"svg",
		attrs={
			"aria-hidden": "true",
			"fill": "currentColor",
			"focusable": "false",
			"height": "16",
			"viewBox": GLYPH_VIEWBOX,
			"width": "14",
			"xmlns": "http://www.w3.org/2000/svg",
		},
		styles={
			"color": refs["accent"],
			"display": "block",
			"flexShrink": 0,
			"height": "16px",
			"opacity": "0.9",
			"width": "14px",
		},
		children=[
			block(
				"g",
				attrs={"fill": "currentColor", "stroke": "none", "transform": GLYPH_TRANSFORM},
				children=[block("path", attrs={"d": d}) for d in GLYPH_PATHS],
			)
		],
	)


def brand(refs):
	"""Header/footer lockup: the accent monogram, then the wordmark.

	Built as child blocks rather than an innerHTML string, for the same reason as
	``whatsapp_icon``: the renderer parses innerHTML with BeautifulSoup, which
	lowercases attribute names and would turn ``viewBox`` into ``viewbox``,
	leaving the mark unscaled.

	Both marks fill with ``currentColor`` so they inherit refs["ink"] / the
	refs["accent"] var from this tree. Those vars are light-dark() pairs, so the
	lockup is correct in either colour scheme without either SVG carrying a
	colour-scheme rule of its own.

	The wordmark is 21px: the two "o" shapes are a lemniscate and merge into a
	blob below roughly 16px, so 19px was the floor and 21px reads more clearly.
	"""
	color = refs["ink"]
	return block(
		"a",
		name="Brand",
		attrs={"href": "/"},
		styles={
			"alignItems": "center",
			"color": color,
			"display": "flex",
			"flexDirection": "row",
			"gap": "9px",
			"height": "fit-content",
			"textDecoration": "none",
			"whiteSpace": "nowrap",
			"width": "fit-content",
		},
		children=[
			brand_glyph(refs),
			block(
				"svg",
				attrs={
					"aria-hidden": "true",
					"fill": "currentColor",
					"focusable": "false",
					"height": "21",
					"viewBox": LOGO_VIEWBOX,
					"width": "62",
					"xmlns": "http://www.w3.org/2000/svg",
				},
				styles={"display": "block", "flexShrink": 0, "height": "21px", "width": "62px"},
				children=[block("path", attrs={"d": LOGO_PATH})],
			),
			# The marks are decorative, so the link still needs an accessible name.
			# Kept bound to Shop Settings so renaming the store still renames the
			# home link for screen readers and link text.
			block(
				"span",
				text="Shop",
				styles={
					"borderWidth": "0",
					"clip": "rect(0, 0, 0, 0)",
					"height": "1px",
					"margin": "-1px",
					"overflow": "hidden",
					"padding": "0",
					"position": "absolute",
					"whiteSpace": "nowrap",
					"width": "1px",
				},
				dynamicValues=[dv("store.name", "innerHTML")],
			),
		],
	)


def nav(refs):
	link_style = {**mono(size="11px", color=refs["ink"], spacing="0.14em"), "textDecoration": "none"}
	badge = block(
		"span",
		text="0",
		attrs={"data-shop": "cart-count", "data-empty": "true"},
		styles={
			"alignItems": "center",
			"backgroundColor": refs["ink"],
			"borderRadius": "999px",
			"color": refs["paper"],
			"display": "flex",
			"fontFamily": MONO,
			"fontSize": "10px",
			"height": "18px",
			"justifyContent": "center",
			"minWidth": "18px",
			"padding": "0 5px",
		},
	)
	cart_link = block(
		"a",
		name="Cart Link",
		attrs={"href": "/cart", "data-shop": "cart-toggle"},
		styles={
			"alignItems": "center",
			"color": refs["ink"],
			"display": "flex",
			"flexDirection": "row",
			"gap": "8px",
			"height": "fit-content",
			"textDecoration": "none",
			"width": "fit-content",
		},
		children=[block("span", text="Cart", styles=dict(link_style)), badge],
	)
	capsule = block(
		"div",
		name="Capsule",
		styles={
			"alignItems": "center",
			"backgroundColor": refs["paper"],
			"borderColor": refs["line"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"display": "flex",
			"flexDirection": "row",
			"gap": "32px",
			"justifyContent": "space-between",
			"maxWidth": "1000px",
			"padding": "13px 24px",
			"width": "100%",
		},
		mobile={"gap": "12px", "padding": "11px 16px"},
		children=[
			brand(refs),
			block(
				"div",
				styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "26px"},
				mobile={"gap": "14px"},
				children=[
					block("a", text="Shop", attrs={"href": "/products"}, styles=dict(link_style)),
					block("a", text="About", attrs={"href": "/about"}, styles=dict(link_style), mobile={"display": "none"}),
					block("a", text="Contact", attrs={"href": "/contact"}, styles=dict(link_style), mobile={"display": "none"}),
					block(
						"a",
						text="Account",
						attrs={"href": "/account/orders"},
						styles=dict(link_style),
						dynamicValues=[
							dv("store.account_label", "innerHTML"),
							dv("store.account_url", "href", "attribute"),
						],
					),
					cart_link,
				],
			),
		],
	)
	return block(
		"div",
		name="Nav",
		styles={
			"display": "flex",
			"justifyContent": "center",
			"left": "0",
			"padding": "0 20px",
			"position": "fixed",
			"right": "0",
			"top": "16px",
			"width": "100%",
			"zIndex": "70",
		},
		mobile={"padding": "0 12px", "top": "10px"},
		children=[capsule],
	)


def footer_column(refs, title, links):
	return block(
		"div",
		styles={"display": "flex", "flexDirection": "column", "gap": "10px", "width": "100%"},
		children=[
			block("p", text=title, styles=mono(size="11px", color=refs["muted"], spacing="0.16em")),
			*[
				block(
					"a",
					text=text,
					attrs={"href": href},
					styles={**mono(size="12px", color=refs["ink"], spacing="0.1em"), "textDecoration": "none"},
				)
				for text, href in links
			],
		],
	)


def footer(refs):
	"""Sits on the canvas rather than in a panel so it stays out of the way."""
	inner = block(
		"div",
		name="Footer Inner",
		styles={"display": "flex", "flexDirection": "column", "gap": "28px", "width": "100%"},
		mobile={"gap": "22px"},
		children=[
			block(
				"div",
				styles={
					"display": "flex",
					"flexDirection": "row",
					"gap": "48px",
					"justifyContent": "space-between",
					"width": "100%",
				},
				mobile={"flexDirection": "column", "gap": "26px"},
				children=[
					block(
						"div",
						styles={"display": "flex", "flexDirection": "column", "gap": "12px", "maxWidth": "300px", "width": "100%"},
						children=[
							brand(refs),
							prose(
								refs,
								"Everyday essentials, from brand-new finds to gently preloved favorites.",
								size="14px",
							),
						],
					),
					block(
						"div",
						styles={
							"display": "grid",
							"gap": "40px",
							"gridTemplateColumns": "repeat(3, minmax(110px, 1fr))",
							"width": "fit-content",
						},
						mobile={"gap": "22px", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "width": "100%"},
						children=[
							footer_column(refs, "Shop", [("All products", "/products"), ("Collections", "/products")]),
							footer_column(refs, "Support", [("Contact", "/contact"), ("FAQ", "/faq")]),
							footer_column(refs, "Legal", [("Privacy", "/about"), ("Terms", "/about")]),
						],
					),
				],
			),
			block(
				"div",
				styles={
					"alignItems": "center",
					"borderTopColor": refs["line"],
					"borderTopStyle": "solid",
					"borderTopWidth": "1px",
					"display": "flex",
					"flexDirection": "row",
					"gap": "6px",
					"paddingTop": "24px",
					"width": "100%",
				},
				children=[
					block("span", text="© 2026", styles=mono(size="11px", color=refs["muted"], spacing="0.12em")),
					block(
						"span",
						text="Shop",
						styles=mono(size="11px", color=refs["muted"], spacing="0.12em"),
						dynamicValues=[dv("store.name", "innerHTML")],
					),
					block("span", text="· All rights reserved", styles=mono(size="11px", color=refs["muted"], spacing="0.12em")),
				],
			),
		],
	)
	return block(
		"div",
		name="Footer",
		styles={
			"display": "flex",
			"flexShrink": 0,
			"justifyContent": "center",
			"marginTop": "auto",
			"padding": "40px 0 48px",
			"width": "100%",
		},
		mobile={"padding": "28px 0 36px"},
		children=[
			block(
				"div",
				styles={"display": "flex", "maxWidth": "1040px", "padding": "0 20px", "width": "100%"},
				mobile={"padding": "0 12px"},
				children=[inner],
			)
		],
	)


def lightbox():
	"""Fullscreen image preview, opened by clicking a product photo.

	Plain markup with no product data bound to it: the image is filled in by
	storefront.js from whichever photo was clicked. That is what lets one overlay
	serve every image on the page instead of being re-rendered per product, and it
	is why the img starts with no src - an empty one would show a broken icon
	behind the backdrop for the moment before the click handler runs.

	The stage carries no data-shop value on purpose. The document-level click
	handler resolves the nearest [data-shop] ancestor, so an unlabelled stage makes
	a click on the photo itself fall through to the overlay root and do nothing,
	leaving the backdrop and the close button as the only ways out.
	"""
	return block(
		"div",
		name="Image Preview",
		attrs={
			"data-shop": "lightbox",
			"data-open": "false",
			"data-pinching": "false",
			"role": "dialog",
			"aria-modal": "true",
			"aria-label": "Image preview",
		},
		children=[
			block(
				"div",
				name="Backdrop",
				attrs={"data-shop": "lightbox-backdrop"},
				classes=["lightbox-backdrop"],
			),
			block(
				"div",
				name="Stage",
				classes=["lightbox-stage"],
				children=[
					block(
						"img",
						name="Photo",
						attrs={
							"data-shop": "lightbox-image",
							"alt": "",
							"draggable": "false",
						},
						classes=["lightbox-image"],
					)
				],
			),
			block(
				"button",
				text="×",
				attrs={
					"type": "button",
					"data-shop": "lightbox-close",
					"aria-label": "Close preview",
				},
				classes=["lightbox-close"],
			),
			block(
				"div",
				name="Controls",
				classes=["lightbox-bar"],
				children=[
					block("span", text="Zoom", classes=["lightbox-label"]),
					block(
						"input",
						attrs={
							"type": "range",
							"data-shop": "lightbox-zoom",
							"min": "1",
							"max": "5",
							"step": "0.01",
							"value": "1",
							"aria-label": "Zoom",
						},
						classes=["lightbox-zoom"],
					),
					block(
						"span",
						text="100%",
						attrs={"data-shop": "lightbox-level"},
						classes=["lightbox-label", "lightbox-level"],
					),
				],
			),
		],
	)


def cart_drawer():
	return block(
		"aside",
		name="Cart Drawer",
		attrs={"data-shop": "cart-drawer", "data-open": "false", "aria-label": "Shopping cart"},
		children=[
			block("div", name="Backdrop", attrs={"data-shop": "drawer-backdrop"}, classes=["drawer-backdrop"]),
			block(
				"div",
				name="Panel",
				classes=["drawer-panel"],
				children=[
					block(
						"div",
						name="Drawer Header",
						classes=["drawer-header"],
						children=[
							block("h2", text="Your cart", classes=["drawer-title"]),
							block(
								"button",
								text="×",
								attrs={"type": "button", "data-shop": "drawer-close", "aria-label": "Close cart"},
								classes=["drawer-close"],
							),
						],
					),
					block("div", name="Drawer Items", attrs={"data-shop": "drawer-items"}, classes=["drawer-items"]),
					block(
						"div",
						name="Drawer Footer",
						classes=["drawer-footer"],
						children=[
							block(
								"div",
								classes=["drawer-total-row"],
								children=[
									block("span", text="Subtotal"),
									block("span", text="", attrs={"data-shop": "drawer-total"}),
								],
							),
							block("p", text="Shipping and taxes calculated at checkout.", classes=["drawer-note"]),
							block(
								"div",
								classes=["drawer-actions"],
								children=[
									block("a", text="View cart", attrs={"href": "/cart"}, classes=["drawer-view"]),
									block("a", text="Checkout", attrs={"href": "/checkout"}, classes=["drawer-checkout"]),
								],
							),
						],
					),
				],
			),
		],
	)


def error_banner(refs):
	return block(
		"div",
		name="Error",
		text="",
		attrs={"data-shop": "error", "role": "alert"},
		styles={
			"borderColor": refs["accent"],
			"borderRadius": "12px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"color": refs["accent"],
			"display": "none",
			"fontSize": "13px",
			"lineHeight": "1.5",
			"padding": "12px 16px",
			"width": "100%",
		},
	)


def page_header(refs, index, title, subtitle=None, extra=None, aside=None):
	"""Headings sit straight on the dot canvas; content lives in the panels below."""
	children = [label(refs, index), display(refs, title, size="38px", mobile_size="26px", element="h1")]
	if subtitle:
		children.append(prose(refs, subtitle, size="14px", width="min(520px, 100%)"))
	children.extend(extra or [])
	stacked = block(
		"div",
		styles={
			"display": "flex",
			"flexDirection": "column",
			"flexGrow": "1",
			"gap": "12px",
			"minWidth": "0px",
			"width": "100%",
		},
		children=children,
	)
	return block(
		"div",
		name="Page Header",
		styles={
			"alignItems": "flex-end",
			"display": "flex",
			"flexDirection": "row",
			"gap": "24px",
			"justifyContent": "space-between",
			"padding": "26px 4px 6px",
			"width": "100%",
		},
		mobile={"alignItems": "stretch", "flexDirection": "column", "gap": "14px", "padding": "16px 4px 2px"},
		children=[stacked, aside] if aside else [stacked],
	)


def hero(refs):
	# Two columns: the copy on the left, and on the right a box of products that
	# can actually be bought, drawn fresh on every visit. The copy column grows to
	# fill whatever is left so the box can hold a fixed width without the two
	# fighting over it.
	# The eyebrow, headline, lede and buttons stay one tight cluster: spreading
	# all five evenly across the column pulls the headline away from its own lede
	# and the hero stops reading as a single statement. Only the spec strip is
	# pinned to the bottom, so the space the taller product box leaves is
	# deliberate rather than a gap under the buttons.
	cluster = block(
		"div",
		name="Hero Cluster",
		styles={"display": "flex", "flexDirection": "column", "gap": "20px", "width": "100%"},
		mobile={"gap": "18px"},
		children=[
			label(refs, "( 01 ) New drop"),
			block(
				"h1",
				text="Fewer things.<br>Collected properly.",
				# The class is what the theme's own CSS sizes this at on a phone.
				# A fixed mobileStyles font-size here would tie with it on
				# specificity and leave the winner to source order.
				classes=["hero__title"],
				styles={
					"color": refs["ink"],
					"fontFamily": HEAD,
					"fontSize": "62px",
					"fontWeight": "500",
					"height": "fit-content",
					"letterSpacing": "-0.03em",
					"lineHeight": "1.02",
					# Wide enough that "Collected properly." stays on one line.
					# It is the longest of the two and the hero has a product box
					# beside it now, so a narrower column wraps it to three lines
					# and the hero stops reading as the statement it was.
					"maxWidth": "620px",
					"width": "100%",
				},
			),
			prose(
				refs,
				"A short catalogue of everyday objects. Considered materials, honest prices "
				"and nothing in the box you will not use.",
				size="15px",
				width="min(460px, 100%)",
			),
			block(
				"div",
				styles={"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "10px", "marginTop": "4px"},
				children=[
					pill(refs, "Shop all", href="/products"),
					pill(refs, "Collections", href="/products", variant="outline"),
				],
			),
		],
	)
	copy = block(
		"div",
		name="Hero Copy",
		styles={
			"display": "flex",
			"flexDirection": "column",
			"flexBasis": "0",
			"flexGrow": 1,
			"gap": "20px",
			# The product box is the taller of the two. align-items:stretch on the
			# row already matches this column to it; space-between then pins the
			# cluster to the top and the strip to the bottom.
			# No height here: the row's height is content-driven, so a percentage
			# height resolves against nothing and collapses the column back to its
			# natural size, undoing the stretch.
			"justifyContent": "space-between",
			"minWidth": "0",
			"width": "100%",
		},
		mobile={"flexBasis": "auto", "flexGrow": 0, "gap": "18px", "justifyContent": "flex-start"},
		children=[
			cluster,
			spec_strip(refs, ["48h dispatch", "14 day returns", "Free shipping", "Cash on delivery"]),
		],
	)
	showcase = block(
		"div",
		name="Hero Showcase",
		styles={
			# No background and no radius: the box was a grey panel the cards sat
			# inside, which made the carousel look like a framed widget rather than
			# the hero's own content. overflow stays, so the cards are still cut
			# off cleanly at the edge rather than spilling across the headline.
			# Wider than one card, because the carousel's cards sit outside the
			# centre one and have to be clipped by the edge of this box. overflow
			# is what turns them into a coverflow rather than cards spilling
			# across the hero.
			"flexBasis": "330px",
			"flexGrow": 0,
			"flexShrink": 0,
			"minWidth": "0",
			"overflow": "hidden",
			"padding": "16px",
			"width": "330px",
		},
		mobile={"flexBasis": "auto", "flexShrink": 1, "width": "100%"},
		tablet={"flexBasis": "auto", "width": "100%"},
		children=[
			# repeater() rather than product_grid(): the grid would put
			# display:grid on the block, which ties with the .carousel__list rule
			# on specificity and leaves the winner to source order. The carousel's
			# layout is absolute positioning, so theme_css has to own it outright.
			repeater(
				"hero_products",
				component_ref("dot-product-card"),
				{"width": "100%"},
				classes=["hero-showcase__grid", "carousel__list"],
				name="Grid · hero",
			)
		],
	)
	return panel(
		refs,
		[
			block(
				"div",
				name="Hero Row",
				styles={
					"alignItems": "stretch",
					"display": "flex",
					"flexDirection": "row",
					"gap": "32px",
					"width": "100%",
				},
				# Stacked, not squeezed, from the tablet breakpoint up. Two columns
				# need about 540px of copy beside a 330px carousel, which is a
				# viewport of roughly 1000px; between 577px and there the copy column
				# was being squeezed to around 140px and the headline wrapped to six
				# lines. The cards are 4:5 portraits too, and a narrow two-column
				# grid of them turns into postage stamps.
				mobile={"flexDirection": "column", "gap": "26px"},
				tablet={"flexDirection": "column", "gap": "30px"},
				children=[copy, showcase],
			),
		],
		styles={"gap": "20px", "padding": "56px 40px 34px"},
		mobile={"gap": "18px", "padding": "30px 18px 22px"},
		name="Hero",
	)


def condition_tag(refs, key, size="10px", padding="5px 12px"):
	"""Mono pill with the product's condition, shown above its name.

	``key`` is the dataScript path — ``product.condition`` on the product
	page, the row's bare ``condition`` inside a card — and a product
	without a condition hides the tag entirely."""
	return block(
		"span",
		text="Condition",
		visibilityCondition={"key": key, "comesFrom": "dataScript"},
		styles={
			**mono(size=size, color=refs["ink"], spacing="0.14em"),
			"borderColor": refs["ink"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"padding": padding,
		},
		dynamicValues=[dv(key, "innerHTML")],
	)


def product_card(refs):
	well = block(
		"div",
		name="Image Well",
		styles={
			"aspectRatio": "4 / 5",
			"backgroundColor": refs["card"],
			"borderRadius": "14px",
			"display": "flex",
			"overflow": "hidden",
			"width": "100%",
		},
		children=[
			block(
				"img",
				attrs={"src": "/assets/builder/images/fallback.png", "alt": "", "loading": "lazy"},
				styles={"display": "block", "height": "100%", "objectFit": "cover", "width": "100%"},
				dynamicValues=[dv("image", "src", "attribute"), dv("product_name", "alt", "attribute")],
			)
		],
	)
	price_row = block(
		"div",
		name="Card Price",
		styles={
			"alignItems": "baseline",
			"display": "flex",
			"flexDirection": "row",
			"flexWrap": "wrap",
			"gap": "4px 10px",
			"width": "100%",
		},
		children=[
			block(
				"p",
				text="",
				visibilityCondition={"key": "formatted_price", "comesFrom": "dataScript"},
				styles=mono(size="13px", weight="500", color=refs["ink"], spacing="0.04em", upper=False),
				dynamicValues=[dv("formatted_price", "innerHTML")],
			),
			block(
				"span",
				text="",
				visibilityCondition={"key": "formatted_compare_at", "comesFrom": "dataScript"},
				styles={
					**mono(size="11px", color=refs["muted"], spacing="0.04em", upper=False),
					"textDecoration": "line-through",
				},
				dynamicValues=[dv("formatted_compare_at", "innerHTML")],
			),
			block(
				"div",
				visibilityCondition={"key": "discount_pct", "comesFrom": "dataScript"},
				styles={"display": "flex", "flexDirection": "row", "width": "fit-content"},
				children=[
					run(
						refs,
						[(False, "−"), (True, "discount_pct"), (False, "%")],
						size="11px",
						color=refs["accent"],
						family=MONO,
					)
				],
			),
		],
	)
	rating_row = block(
		"div",
		name="Card Rating",
		visibilityCondition={"key": "rating_count", "comesFrom": "dataScript"},
		styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "6px", "width": "fit-content"},
		children=[
			stars_span(refs, "rating_stars", size="11px"),
			run(refs, [(False, "("), (True, "rating_count"), (False, ")")], size="11px", family=MONO),
		],
	)
	return block(
		"a",
		name="Product Card",
		attrs={"href": "#"},
		styles={
			"color": refs["ink"],
			"display": "flex",
			"flexDirection": "column",
			"gap": "12px",
			"textDecoration": "none",
			"width": "100%",
		},
		dynamicValues=[dv("route", "href", "attribute")],
		children=[
			well,
			condition_tag(refs, "condition"),
			block(
				"h3",
				text="Product",
				styles={
					"fontSize": "14px",
					"fontWeight": "500",
					"height": "fit-content",
					"letterSpacing": "-0.01em",
					"lineHeight": "1.35",
					"width": "100%",
				},
				dynamicValues=[dv("product_name", "innerHTML")],
			),
			rating_row,
			price_row,
		],
	)


def stars_span(refs, key, size="12px"):
	return block(
		"span",
		text="★★★★★",
		styles={
			"color": refs["ink"],
			"fontSize": size,
			"height": "fit-content",
			"letterSpacing": "1px",
			"lineHeight": "1",
			"width": "fit-content",
		},
		dynamicValues=[dv(key, "innerHTML")],
	)


def product_grid(refs, key, source, columns=4, gap="34px 20px", classes=None):
	return repeater(
		key,
		component_ref("dot-product-card"),
		{
			"display": "grid",
			"gap": gap,
			"gridTemplateColumns": f"repeat({columns}, minmax(0, 1fr))",
			"width": "100%",
		},
		mobile={"gap": "22px 12px", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))"},
		tablet={"gridTemplateColumns": "repeat(2, minmax(0, 1fr))"},
		classes=classes,
		name=f"Grid · {source}",
	)


def collection_tile(refs):
	photo = block(
		"div",
		name="Tile Photo",
		styles={"backgroundPosition": "center", "backgroundSize": "cover", "inset": "0", "position": "absolute"},
		dynamicValues=[dv("image_css", "background-image", "style")],
	)
	title_pill = block(
		"span",
		text="Collection",
		styles={
			**mono(size="11px", weight="500", color=refs["ink"], spacing="0.12em"),
			"backgroundColor": refs["paper"],
			"borderRadius": "999px",
			"padding": "9px 16px",
			"position": "relative",
		},
		dynamicValues=[dv("title", "innerHTML")],
	)
	return block(
		"a",
		name="Collection Tile",
		attrs={"href": "#"},
		styles={
			"alignItems": "flex-start",
			"backgroundColor": refs["card"],
			"borderRadius": "16px",
			"color": refs["ink"],
			"display": "flex",
			"flexDirection": "column",
			"justifyContent": "flex-end",
			"minHeight": "210px",
			"overflow": "hidden",
			"padding": "16px",
			"position": "relative",
			"textDecoration": "none",
			"width": "100%",
		},
		dynamicValues=[dv("route", "href", "attribute")],
		children=[photo, title_pill],
	)


def filter_bar(refs):
	option_chip = block(
		"a",
		name="Filter Option",
		text="Option",
		attrs={"href": "#", "data-active": "false"},
		styles={
			"borderColor": refs["line"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"color": refs["ink"],
			"fontFamily": MONO,
			"fontSize": "10px",
			"height": "fit-content",
			"letterSpacing": "0.06em",
			"padding": "6px 12px",
			"textDecoration": "none",
			"whiteSpace": "nowrap",
			"width": "fit-content",
		},
		dynamicValues=[
			dv("url", "href", "attribute"),
			dv("label", "innerHTML"),
			dv("active", "data-active", "attribute"),
		],
	)
	filter_group = block(
		"div",
		name="Filter Group",
		styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "14px", "width": "100%"},
		mobile={"alignItems": "flex-start", "flexDirection": "column", "gap": "6px"},
		children=[
			block(
				"p",
				text="Filter",
				styles={
					**mono(size="9px", color=refs["muted"], spacing="0.14em"),
					"flexShrink": 0,
					"minWidth": "74px",
				},
				dynamicValues=[dv("label", "innerHTML")],
			),
			repeater(
				"options",
				option_chip,
				{"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "6px", "width": "100%"},
				name="Filter Options",
			),
		],
	)
	return repeater(
		"filters",
		filter_group,
		{"display": "flex", "flexDirection": "column", "gap": "8px", "width": "100%"},
		name="Filters",
	)


def review_card(refs):
	return block(
		"div",
		name="Review",
		styles={
			"borderBottomColor": refs["line"],
			"borderBottomStyle": "solid",
			"borderBottomWidth": "1px",
			"display": "flex",
			"flexDirection": "column",
			"gap": "8px",
			"padding": "20px 0",
			"width": "100%",
		},
		children=[
			stars_span(refs, "stars", size="12px"),
			block(
				"h3",
				text="Review title",
				styles={"fontSize": "14px", "fontWeight": "500", "height": "fit-content", "width": "100%"},
				dynamicValues=[dv("title", "innerHTML")],
			),
			block(
				"p",
				text="",
				styles={"color": refs["muted"], "fontSize": "13px", "height": "fit-content", "lineHeight": "1.6", "width": "100%"},
				dynamicValues=[dv("review", "innerHTML")],
			),
			block(
				"div",
				styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "10px", "width": "100%"},
				children=[
					run(refs, [(True, "reviewer_name"), (False, " · "), (True, "posted_on")], size="10px", family=MONO),
					block(
						"span",
						text="Verified buyer",
						visibilityCondition={"key": "verified", "comesFrom": "dataScript"},
						styles=mono(size="10px", color=refs["success"], spacing="0.12em"),
					),
				],
			),
		],
	)


def delivery_card(refs):
	line = lambda text, **extra: block(
		"p",
		text=text,
		styles={"color": refs["muted"], "fontSize": "12px", "height": "fit-content", "lineHeight": "1.5", "width": "100%"},
		**extra,
	)
	return block(
		"div",
		name="Delivery",
		styles={
			"backgroundColor": refs["card"],
			"borderRadius": "14px",
			"display": "flex",
			"flexDirection": "column",
			"gap": "6px",
			"padding": "16px 18px",
			"width": "100%",
		},
		children=[
			block("p", text="Free delivery", styles=mono(size="11px", color=refs["ink"], spacing="0.12em")),
			line("Ships in 48 hours. 14 day easy returns."),
			line(
				"Cash on delivery available.",
				visibilityCondition={"key": "store.enable_cod", "comesFrom": "dataScript"},
			),
		],
	)


def trust_row(refs):
	return spec_strip(refs, ["Secure payments", "Easy returns", "Quality checked", "Support that replies"])


def home_blocks(refs):
	collections = panel(
		refs,
		[
			section_head(refs, "( 02 ) Collections", "Shop by collection", "All products →", "/products"),
			repeater(
				"collections",
				component_ref("dot-collection-tile"),
				{
					"display": "grid",
					"gap": "16px",
					"gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
					"width": "100%",
				},
				mobile={"gridTemplateColumns": "minmax(0, 1fr)"},
				tablet={"gridTemplateColumns": "repeat(2, minmax(0, 1fr))"},
				name="Grid · collections",
			),
		],
		name="Section · Collections",
	)
	best_sellers = panel(
		refs,
		[
			section_head(refs, "( 03 ) New arrival", "What is New", "View all →", "/products"),
			product_grid(refs, "featured_products", "featured"),
		],
		name="Section · Best Sellers",
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			# The hero is inlined rather than pulled in as component_ref("dot-hero"),
			# because it now holds a product grid of its own and the builder does not
			# resolve a component reference nested inside a component: the cards
			# rendered as unstyled shells, with their data bound and their styles
			# missing, so the box came out empty. At page level the card reference
			# resolves the same way section 03's does.
			stack([hero(refs), collections, best_sellers]),
			component_ref("dot-footer"),
		],
	)


def filter_toggle(refs):
	node = pill(
		refs,
		"",
		variant="outline",
		attrs={"data-shop": "filter-toggle", "aria-expanded": "false", "aria-controls": "filters"},
		name="Filter Toggle",
	)
	node["baseStyles"].update({"alignItems": "center", "display": "flex", "gap": "8px", "padding": "9px 18px"})
	node.pop("innerHTML", None)
	node["children"] = [
		block("span", text="Filters", styles={"fontSize": "11px", "letterSpacing": "0.14em", "width": "fit-content"}),
		block(
			"span",
			text="",
			name="Applied Count",
			classes=["filter-count"],
			visibilityCondition={"key": "filters_applied", "comesFrom": "dataScript"},
			styles={
				"alignItems": "center",
				"backgroundColor": refs["ink"],
				"borderRadius": "999px",
				"color": refs["paper"],
				"display": "flex",
				"fontSize": "9px",
				"height": "16px",
				"justifyContent": "center",
				"minWidth": "16px",
				"padding": "0 4px",
			},
			dynamicValues=[dv("filter_count", "innerHTML")],
		),
	]
	return node


def listing_controls(refs):
	return block(
		"div",
		name="Listing Controls",
		styles={
			"alignItems": "center",
			"display": "flex",
			"flexDirection": "row",
			"flexShrink": "0",
			"flexWrap": "wrap",
			"gap": "8px",
			"justifyContent": "flex-end",
			"width": "fit-content",
		},
		mobile={"justifyContent": "flex-start", "width": "100%"},
		children=[filter_toggle(refs), search_form(refs)],
	)


def search_form(refs):
	go = pill(refs, "Go", attrs={"type": "submit"})
	go["baseStyles"]["padding"] = "10px 20px"
	return block(
		"form",
		name="Search",
		attrs={"data-shop": "search-form", "action": "/products"},
		styles={"display": "flex", "flexDirection": "row", "gap": "8px", "width": "fit-content"},
		mobile={"width": "100%"},
		children=[
			block(
				"input",
				attrs={"type": "search", "name": "search", "placeholder": "Search"},
				dynamicValues=[dv("search", "value", "attribute")],
				styles={
					"backgroundColor": refs["paper"],
					"borderColor": refs["line"],
					"borderRadius": "999px",
					"borderStyle": "solid",
					"borderWidth": "1px",
					"color": refs["ink"],
					"fontSize": "11px",
					"padding": "9px 16px",
					"width": "200px",
				},
				mobile={"width": "100%"},
			),
			go,
		],
	)


def products_blocks(refs):
	active_search = block(
		"div",
		name="Active Search",
		visibilityCondition={"key": "search_label", "comesFrom": "dataScript"},
		styles={"alignItems": "baseline", "display": "flex", "flexDirection": "row", "gap": "12px", "width": "fit-content"},
		children=[
			block(
				"p",
				text="Results",
				styles=mono(size="11px", color=refs["ink"], spacing="0.1em", upper=False),
				dynamicValues=[dv("search_label", "innerHTML")],
			),
			block(
				"a",
				text="Clear",
				attrs={"href": "/products"},
				styles={**mono(size="10px", color=refs["muted"], spacing="0.14em"), "textDecoration": "underline"},
			),
		],
	)
	header = page_header(
		refs,
		"( Catalogue )",
		"All products",
		"Everything in the store, filtered however you like.",
		extra=[active_search],
		aside=listing_controls(refs),
	)
	clear_all = block(
		"div",
		name="Clear Filters",
		visibilityCondition={"key": "filters_applied", "comesFrom": "dataScript"},
		styles={
			"borderTopColor": refs["line"],
			"borderTopStyle": "solid",
			"borderTopWidth": "1px",
			"display": "flex",
			"marginTop": "4px",
			"paddingTop": "12px",
			"width": "100%",
		},
		children=[
			block(
				"a",
				text="Clear all filters",
				attrs={"href": "/products"},
				styles={**mono(size="10px", color=refs["muted"], spacing="0.14em"), "textDecoration": "underline"},
			)
		],
	)
	controls = panel(
		refs,
		[component_ref("dot-filter-bar"), clear_all],
		styles={"padding": "18px 28px"},
		mobile={"padding": "16px 14px"},
		name="Section · Controls",
	)
	controls["attributes"].update({"data-shop": "filter-panel", "data-open": "false", "id": "filters"})
	empty = block(
		"div",
		name="No Results",
		visibilityCondition={"key": "no_results", "comesFrom": "dataScript"},
		styles={
			"alignItems": "center",
			"display": "flex",
			"flexDirection": "column",
			"gap": "12px",
			"padding": "40px 0",
			"width": "100%",
		},
		children=[
			block("p", text="Nothing matches those filters", styles=mono(size="12px", color=refs["ink"], spacing="0.1em")),
			block(
				"a",
				text="Clear all",
				attrs={"href": "/products"},
				styles={**mono(size="10px", color=refs["muted"], spacing="0.14em"), "textDecoration": "underline"},
			),
		],
	)
	grid = panel(refs, [product_grid(refs, "products", "products"), empty], name="Section · Product Grid")
	return shell(
		refs,
		[component_ref("dot-navbar"), stack([header, controls, grid]), component_ref("dot-footer")],
	)


def collection_blocks(refs):
	title = display(refs, "Collection", size="38px", mobile_size="26px", element="h1")
	title["dynamicValues"] = [dv("collection.title", "innerHTML")]
	description = block(
		"p",
		text="",
		visibilityCondition={"key": "collection.description", "comesFrom": "dataScript"},
		styles={
			"color": refs["muted"],
			"fontSize": "14px",
			"height": "fit-content",
			"lineHeight": "1.65",
			"width": "min(520px, 100%)",
		},
		dynamicValues=[dv("collection.description", "innerHTML")],
	)
	heading = block(
		"div",
		styles={
			"display": "flex",
			"flexDirection": "column",
			"flexGrow": "1",
			"gap": "12px",
			"minWidth": "0px",
			"width": "100%",
		},
		children=[label(refs, "( Collection )"), title, description],
	)
	header = block(
		"div",
		name="Page Header",
		styles={
			"alignItems": "flex-end",
			"display": "flex",
			"flexDirection": "row",
			"gap": "24px",
			"justifyContent": "space-between",
			"padding": "26px 4px 6px",
			"width": "100%",
		},
		mobile={"alignItems": "stretch", "flexDirection": "column", "gap": "14px", "padding": "16px 4px 2px"},
		children=[heading, filter_toggle(refs)],
	)
	clear_link = block(
		"a",
		text="Clear all filters",
		attrs={"href": "#"},
		dynamicValues=[dv("clear_url", "href", "attribute")],
		styles={**mono(size="10px", color=refs["muted"], spacing="0.14em"), "textDecoration": "underline"},
	)
	clear_all = block(
		"div",
		name="Clear Filters",
		visibilityCondition={"key": "filters_applied", "comesFrom": "dataScript"},
		styles={
			"borderTopColor": refs["line"],
			"borderTopStyle": "solid",
			"borderTopWidth": "1px",
			"display": "flex",
			"marginTop": "4px",
			"paddingTop": "12px",
			"width": "100%",
		},
		children=[clear_link],
	)
	controls = panel(
		refs,
		[component_ref("dot-filter-bar"), clear_all],
		styles={"padding": "18px 28px"},
		mobile={"padding": "16px 14px"},
		name="Section · Controls",
	)
	controls["attributes"].update({"data-shop": "filter-panel", "data-open": "false", "id": "filters"})
	empty = block(
		"div",
		name="No Results",
		visibilityCondition={"key": "no_results", "comesFrom": "dataScript"},
		styles={
			"alignItems": "center",
			"display": "flex",
			"flexDirection": "column",
			"gap": "12px",
			"padding": "40px 0",
			"width": "100%",
		},
		children=[
			block("p", text="Nothing matches those filters", styles=mono(size="12px", color=refs["ink"], spacing="0.1em")),
			block(
				"a",
				text="Clear all",
				attrs={"href": "#"},
				dynamicValues=[dv("clear_url", "href", "attribute")],
				styles={**mono(size="10px", color=refs["muted"], spacing="0.14em"), "textDecoration": "underline"},
			),
		],
	)
	grid = panel(
		refs, [product_grid(refs, "products", "collection"), empty], name="Section · Collection Grid"
	)
	return shell(
		refs,
		[component_ref("dot-navbar"), stack([header, controls, grid]), component_ref("dot-footer")],
	)


def inset(refs, children, styles=None, **extra):
	base = {
		"backgroundColor": refs["card"],
		"borderRadius": "14px",
		"display": "flex",
		"flexDirection": "column",
		"gap": "6px",
		"padding": "18px 20px",
		"width": "100%",
	}
	base.update(styles or {})
	return block("div", styles=base, children=children, **extra)


def field_styles(refs, radius="12px"):
	return {
		"backgroundColor": refs["paper"],
		"borderColor": refs["line"],
		"borderRadius": radius,
		"borderStyle": "solid",
		"borderWidth": "1px",
		"color": refs["ink"],
		"fontSize": "12px",
		"padding": "12px 14px",
		"width": "100%",
	}


def money_row(refs, text, bound_key=None, static_value=None, strong=False):
	return block(
		"div",
		styles={"display": "flex", "flexDirection": "row", "justifyContent": "space-between", "width": "100%"},
		children=[
			block(
				"p",
				text=text,
				styles=mono(size="11px", color=refs["ink"] if strong else refs["muted"], spacing="0.12em"),
			),
			block(
				"p",
				text=static_value or "",
				styles=mono(
					size="14px" if strong else "12px",
					weight="500" if strong else "400",
					color=refs["success"] if static_value == "Free" else refs["ink"],
					spacing="0.04em",
					upper=False,
				),
				dynamicValues=[dv(bound_key, "innerHTML")] if bound_key else [],
			),
		],
	)


def discount_row(refs, bound_key, condition_key):
	return block(
		"div",
		name="Discount Row",
		visibilityCondition={"key": condition_key, "comesFrom": "dataScript"},
		styles={"display": "flex", "flexDirection": "row", "justifyContent": "space-between", "width": "100%"},
		children=[
			block("p", text="Discount", styles=mono(size="11px", color=refs["muted"], spacing="0.12em")),
			run(refs, [(False, "−"), (True, bound_key)], size="12px", color=refs["accent"], family=MONO),
		],
	)


def breadcrumb(refs, trail_key):
	crumb = {**mono(size="10px", color=refs["muted"], spacing="0.14em"), "textDecoration": "none"}
	return block(
		"div",
		name="Breadcrumb",
		styles={
			"alignItems": "center",
			"display": "flex",
			"flexDirection": "row",
			"gap": "8px",
			"padding": "20px 4px 0",
			"width": "100%",
		},
		children=[
			block("a", text="Home", attrs={"href": "/"}, styles=dict(crumb)),
			block("span", text="/", styles=dict(crumb)),
			block("a", text="Products", attrs={"href": "/products"}, styles=dict(crumb)),
			block("span", text="/", styles=dict(crumb)),
			block("span", text="Product", styles={**crumb, "color": refs["ink"]}, dynamicValues=[dv(trail_key, "innerHTML")]),
		],
	)


def pdp_gallery(refs):
	thumb = block(
		"img",
		name="Thumbnail",
		attrs={
			"src": "/assets/builder/images/fallback.png",
			"alt": "",
			"loading": "lazy",
			"data-shop": "thumb",
			"data-selected": "false",
		},
		styles={
			"aspectRatio": "1 / 1",
			"backgroundColor": refs["card"],
			"borderColor": refs["line"],
			"borderRadius": "10px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"cursor": "pointer",
			"display": "block",
			"objectFit": "cover",
			"width": "66px",
		},
		dynamicValues=[
			dv("image", "src", "attribute"),
			dv("image", "data-image", "attribute"),
			dv("alt_text", "alt", "attribute"),
		],
	)
	return block(
		"div",
		name="Gallery",
		styles={"display": "flex", "flexDirection": "column", "gap": "12px", "width": "100%"},
		children=[
			block(
				"div",
				name="Image Well",
				styles={
					"aspectRatio": "1 / 1",
					"backgroundColor": refs["card"],
					"borderRadius": "16px",
					"display": "flex",
					"overflow": "hidden",
					"width": "100%",
				},
				children=[
					block(
						"img",
						name="Main Image",
						attrs={
							"src": "/assets/builder/images/fallback.png",
							"alt": "",
							"loading": "eager",
							"data-shop": "main-image",
						},
						styles={"display": "block", "height": "100%", "objectFit": "cover", "width": "100%"},
						dynamicValues=[
							dv("product.image", "src", "attribute"),
							dv("product.product_name", "alt", "attribute"),
						],
					)
				],
			),
			repeater(
				"product.images",
				thumb,
				{"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "10px", "width": "100%"},
				name="Thumbnails",
			),
		],
	)


def pdp_price(refs):
	price_row = block(
		"div",
		styles={"alignItems": "baseline", "display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "12px", "width": "100%"},
		children=[
			block(
				"p",
				text="",
				attrs={"data-shop": "pdp-price"},
				styles=mono(size="26px", weight="500", color=refs["ink"], spacing="-0.01em", upper=False),
				dynamicValues=[dv("product.formatted_price", "innerHTML")],
			),
			block(
				"span",
				text="",
				visibilityCondition={"key": "product.formatted_compare_at", "comesFrom": "dataScript"},
				styles={
					**mono(size="13px", color=refs["muted"], spacing="0.04em", upper=False),
					"textDecoration": "line-through",
				},
				dynamicValues=[dv("product.formatted_compare_at", "innerHTML")],
			),
			block(
				"div",
				attrs={"data-shop": "pdp-discount"},
				visibilityCondition={"key": "product.discount_pct", "comesFrom": "dataScript"},
				styles={
					"borderColor": refs["accent"],
					"borderRadius": "999px",
					"borderStyle": "solid",
					"borderWidth": "1px",
					"display": "flex",
					"flexDirection": "row",
					"padding": "3px 10px",
					"width": "fit-content",
				},
				children=[
					run(refs, [(True, "product.discount_pct"), (False, "% OFF")], size="10px", color=refs["accent"], family=MONO)
				],
			),
		],
	)
	savings = block(
		"div",
		attrs={"data-shop": "pdp-savings"},
		visibilityCondition={"key": "product.formatted_savings", "comesFrom": "dataScript"},
		styles={"display": "flex", "flexDirection": "row", "width": "fit-content"},
		children=[
			run(refs, [(False, "You save "), (True, "product.formatted_savings")], size="11px", color=refs["accent"], family=MONO)
		],
	)
	return block(
		"div",
		name="Price",
		styles={"display": "flex", "flexDirection": "column", "gap": "6px", "width": "100%"},
		children=[price_row, savings],
	)


def pdp_details(refs):
	option_button = block(
		"button",
		name="Option",
		text="Value",
		attrs={"type": "button", "data-shop": "variant-option"},
		styles={
			"backgroundColor": refs["paper"],
			"borderColor": refs["line"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"color": refs["ink"],
			"fontFamily": MONO,
			"fontSize": "11px",
			"letterSpacing": "0.06em",
			"minWidth": "46px",
			"padding": "10px 16px",
			"width": "fit-content",
		},
		dynamicValues=[
			dv("value", "innerHTML"),
			dv("attribute", "data-attribute", "attribute"),
			dv("value", "data-value", "attribute"),
		],
	)
	attribute_group = block(
		"div",
		name="Attribute",
		styles={"display": "flex", "flexDirection": "column", "gap": "10px", "width": "100%"},
		children=[
			block(
				"p",
				text="Attribute",
				styles=mono(size="10px", color=refs["muted"], spacing="0.16em"),
				dynamicValues=[dv("attribute", "innerHTML")],
			),
			repeater(
				"values",
				option_button,
				{"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "8px", "width": "100%"},
				name="Options",
			),
		],
	)
	stock_line = block(
		"div",
		name="Stock",
		visibilityCondition={"key": "product.in_stock", "comesFrom": "dataScript"},
		styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "8px", "width": "fit-content"},
		children=[
			block(
				"span",
				styles={"backgroundColor": refs["success"], "borderRadius": "50%", "flexShrink": 0, "height": "7px", "width": "7px"},
			),
			block("span", text="In stock, ready to dispatch", styles=mono(size="10px", color=refs["ink"], spacing="0.12em")),
		],
	)
	highlight = block(
		"span",
		name="Highlight",
		text="Highlight",
		styles={
			"borderColor": refs["line"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"color": refs["ink"],
			"fontFamily": MONO,
			"fontSize": "10px",
			"height": "fit-content",
			"letterSpacing": "0.08em",
			"padding": "6px 13px",
			"width": "fit-content",
		},
		dynamicValues=[dv("label", "innerHTML")],
	)
	buy_button = lambda name, text, hook, styles: block(
		"button",
		name=name,
		text=text,
		attrs={
			"type": "button",
			"data-shop": hook,
			"data-label": text,
			"data-added-label": "Added",
			"data-out-of-stock-label": "Out of stock",
		},
		styles=styles,
		dynamicValues=[dv("product.buy_item_code", "data-item-code", "attribute")],
	)
	# Add to cart + Buy now keep the full-width row to themselves; WhatsApp
	# gets its own full-width row underneath on desktop (the inner row still
	# stacks on mobile, exactly as the old flat actions row did).
	buy_row = block(
		"div",
		name="Buy row",
		styles={"display": "flex", "flexDirection": "row", "gap": "10px", "width": "100%"},
		mobile={"flexDirection": "column"},
		children=[
			buy_button(
				"Add to cart",
				"Add to cart",
				"add-to-cart",
				{**pill(refs, "", variant="outline", full=True)["baseStyles"], "flexGrow": "1"},
			),
			buy_button("Buy now", "Buy now", "buy-now", {**pill(refs, "", full=True)["baseStyles"], "flexGrow": "1"}),
		],
	)
	whatsapp_button = block(
		"a",
		name="Buy on WhatsApp",
		attrs={"target": "_blank", "rel": "noopener"},
		children=[whatsapp_icon(), block("span", text="Buy on WhatsApp")],
		styles={
			**pill(refs, "", variant="outline", full=True)["baseStyles"],
			"alignItems": "center",
			# WhatsApp green pill; reset.css's clobbering of the link's
			# colour/underline/background is beaten with !important exactly
			# as directions_button does it.
			"backgroundColor": f"{WHATSAPP_GREEN} !important",
			"borderColor": WHATSAPP_GREEN,
			"color": "#FFFFFF !important",
			"display": "flex",
			"flexDirection": "row",
			"gap": "9px",
			"justifyContent": "center",
			"textDecoration": "none !important",
		},
		dynamicValues=[dv("product.whatsapp_url", "href", "attribute")],
		visibilityCondition={"key": "product.whatsapp_url", "comesFrom": "dataScript"},
	)
	actions = block(
		"div",
		name="Actions",
		styles={"display": "flex", "flexDirection": "column", "gap": "10px", "width": "100%"},
		children=[buy_row, whatsapp_button],
	)
	return block(
		"div",
		name="Details",
		styles={"display": "flex", "flexDirection": "column", "gap": "18px", "width": "100%"},
		children=[
			condition_tag(refs, "product.condition", size="11px", padding="7px 16px"),
			block(
				"h1",
				text="Product",
				styles={
					"color": refs["ink"],
					"fontFamily": HEAD,
					"fontSize": "30px",
					"fontWeight": "500",
					"height": "fit-content",
					"letterSpacing": "-0.02em",
					"lineHeight": "1.15",
					"width": "100%",
				},
				mobile={"fontSize": "24px"},
				dynamicValues=[dv("product.product_name", "innerHTML")],
			),
			pdp_rating_row(refs),
			pdp_price(refs),
			repeater(
				"product.attribute_options",
				attribute_group,
				{"display": "flex", "flexDirection": "column", "gap": "16px", "width": "100%"},
				name="Variant Picker",
			),
			stock_line,
			repeater(
				"product.highlights",
				highlight,
				{"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "8px", "width": "100%"},
				name="Highlights",
			),
			actions,
			error_banner(refs),
			component_ref("dot-delivery-card"),
			block(
				"p",
				text="",
				visibilityCondition={"key": "product.description_text", "comesFrom": "dataScript"},
				styles={"color": refs["muted"], "fontSize": "13px", "height": "fit-content", "lineHeight": "1.7", "width": "100%"},
				dynamicValues=[dv("product.description_text", "innerHTML")],
			),
			component_ref("dot-trust-row"),
		],
	)


def pdp_rating_row(refs):
	return block(
		"div",
		name="Rating",
		visibilityCondition={"key": "product.rating.count", "comesFrom": "dataScript"},
		styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "8px", "width": "fit-content"},
		children=[
			stars_span(refs, "product.rating.stars", size="13px"),
			block(
				"span",
				text="",
				styles=mono(size="11px", color=refs["ink"], spacing="0.06em", upper=False),
				dynamicValues=[dv("product.rating.average", "innerHTML")],
			),
			block(
				"a",
				text="Read reviews",
				attrs={"href": "#reviews"},
				styles={**mono(size="10px", color=refs["muted"], spacing="0.12em"), "textDecoration": "underline"},
			),
		],
	)


def rating_summary(refs):
	histogram_row = block(
		"div",
		name="Histogram Row",
		styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "12px", "width": "100%"},
		children=[
			block(
				"span",
				text="5",
				styles={**mono(size="11px", color=refs["muted"], spacing="0.04em", upper=False), "flexShrink": 0, "width": "10px"},
				dynamicValues=[dv("stars", "innerHTML")],
			),
			block(
				"div",
				styles={
					"backgroundColor": refs["line"],
					"borderRadius": "999px",
					"flexGrow": "1",
					"height": "4px",
					"overflow": "hidden",
					"width": "100%",
				},
				children=[
					block(
						"div",
						styles={"backgroundColor": refs["ink"], "height": "100%", "width": "0%"},
						dynamicValues=[dv("width", "width", "style")],
					)
				],
			),
			block(
				"span",
				text="0",
				styles={
					**mono(size="11px", color=refs["muted"], spacing="0.04em", upper=False),
					"flexShrink": 0,
					"minWidth": "18px",
					"textAlign": "right",
				},
				dynamicValues=[dv("count", "innerHTML")],
			),
		],
	)
	return block(
		"div",
		name="Rating Summary",
		styles={"display": "flex", "flexDirection": "column", "gap": "10px", "height": "fit-content", "width": "100%"},
		children=[
			block(
				"p",
				text="",
				styles=mono(size="52px", weight="500", color=refs["ink"], spacing="-0.03em", upper=False),
				mobile={"fontSize": "40px"},
				dynamicValues=[dv("reviews.average", "innerHTML")],
			),
			stars_span(refs, "product.rating.stars", size="14px"),
			run(refs, [(False, "Based on "), (True, "reviews.count"), (False, " reviews")], size="10px", family=MONO),
			repeater(
				"reviews.histogram",
				histogram_row,
				{"display": "flex", "flexDirection": "column", "gap": "9px", "marginTop": "8px", "width": "100%"},
				name="Histogram",
			),
		],
	)


def reviews_panel(refs):
	node = panel(
		refs,
		[
			section_head(refs, "( Reviews )", "Ratings and reviews"),
			block(
				"div",
				styles={
					"display": "grid",
					"gap": "64px",
					"gridTemplateColumns": "minmax(0, 280px) minmax(0, 1fr)",
					"width": "100%",
				},
				mobile={"gap": "24px", "gridTemplateColumns": "minmax(0, 1fr)"},
				children=[
					rating_summary(refs),
					repeater(
						"reviews.reviews",
						component_ref("dot-review-card"),
						{"display": "flex", "flexDirection": "column", "marginTop": "-20px", "width": "100%"},
						name="Review List",
					),
				],
			),
		],
		name="Section · Reviews",
	)
	node["attributes"]["id"] = "reviews"
	node["visibilityCondition"] = {"key": "reviews.count", "comesFrom": "dataScript"}
	return node


def review_form_panel(refs):
	star = lambda value: block(
		"button",
		text="★",
		attrs={
			"type": "button",
			"data-shop": "rating-star",
			"data-value": str(value),
			"data-selected": "false",
			"aria-label": f"{value} out of 5 stars",
		},
		styles={
			"backgroundColor": "transparent",
			"borderWidth": "0px",
			"color": refs["line"],
			"fontSize": "24px",
			"lineHeight": "1",
			"padding": "0",
			"width": "fit-content",
		},
	)
	form = block(
		"form",
		name="Review Form",
		attrs={"data-shop": "review-form"},
		styles={"display": "none", "flexDirection": "column", "gap": "10px", "maxWidth": "520px", "width": "100%"},
		children=[
			block(
				"div",
				name="Rating Stars",
				styles={"display": "flex", "flexDirection": "row", "gap": "4px"},
				children=[star(value) for value in range(1, 6)],
			),
			input_block(refs, "title", "Title (optional)"),
			block(
				"textarea",
				attrs={"name": "review", "rows": "4", "placeholder": "What did you think?"},
				styles=field_styles(refs),
			),
			pill(refs, "Submit review", attrs={"type": "submit"}),
		],
	)
	return panel(
		refs,
		[
			section_head(refs, "( Write )", "Share your experience"),
			error_banner(refs),
			block(
				"a",
				name="Review Sign-in",
				text="Sign in to write a review",
				attrs={"data-shop": "review-signin", "href": "/login"},
				styles={**mono(size="11px", color=refs["ink"], spacing="0.12em"), "textDecoration": "underline"},
			),
			form,
		],
		styles={"gap": "18px"},
		name="Section · Write a Review",
	)


def buy_bar(refs):
	price = block(
		"span",
		text="",
		attrs={"data-shop": "pdp-price"},
		styles=mono(size="14px", weight="500", color=refs["ink"], spacing="0.02em", upper=False),
		dynamicValues=[dv("product.formatted_price", "innerHTML")],
	)
	buy = block(
		"button",
		name="Bar Buy Now",
		text="Buy now",
		attrs={
			"type": "button",
			"data-shop": "buy-now",
			"data-label": "Buy now",
			"data-out-of-stock-label": "Out of stock",
		},
		styles={**pill(refs, "")["baseStyles"], "padding": "12px 26px"},
		dynamicValues=[dv("product.buy_item_code", "data-item-code", "attribute")],
	)
	return block(
		"div",
		name="Buy Bar",
		classes=["pdp-buybar"],
		children=[block("div", classes=["pdp-buybar-inner"], children=[price, buy])],
	)


def product_blocks(refs):
	main = panel(
		refs,
		[
			block(
				"div",
				styles={
					"display": "grid",
					"gap": "48px",
					"gridTemplateColumns": "minmax(0, 1fr) minmax(0, 1fr)",
					"width": "100%",
				},
				mobile={"gap": "26px", "gridTemplateColumns": "minmax(0, 1fr)"},
				children=[pdp_gallery(refs), pdp_details(refs)],
			)
		],
		name="Section · Product",
	)
	related = panel(
		refs,
		[
			section_head(refs, "( More )", "You may also like", "All products →", "/products"),
			product_grid(refs, "related_products", "related"),
		],
		name="Section · Related",
	)
	blocks = shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack([breadcrumb(refs, "product.product_name"), main, reviews_panel(refs), review_form_panel(refs), related]),
			component_ref("dot-footer"),
			buy_bar(refs),
			# Only the product page opens the preview, so only it carries the
			# overlay. It is a fullscreen layer, so it goes last and is unaffected
			# by anything the sections above do to the stacking order.
			component_ref("dot-lightbox"),
		],
	)
	blocks[0]["baseStyles"]["paddingBottom"] = "72px"
	return blocks


def cart_blocks(refs):
	qty_button = {
		"alignItems": "center",
		"backgroundColor": refs["paper"],
		"borderColor": refs["line"],
		"borderRadius": "999px",
		"borderStyle": "solid",
		"borderWidth": "1px",
		"color": refs["ink"],
		"display": "flex",
		"fontSize": "13px",
		"height": "28px",
		"justifyContent": "center",
		"width": "28px",
	}
	line_item = block(
		"div",
		name="Line Item",
		styles={
			"alignItems": "center",
			"borderBottomColor": refs["line"],
			"borderBottomStyle": "solid",
			"borderBottomWidth": "1px",
			"display": "flex",
			"flexDirection": "row",
			"gap": "16px",
			"padding": "18px 0",
			"width": "100%",
		},
		mobile={"gap": "10px"},
		children=[
			block(
				"img",
				attrs={"src": "/assets/builder/images/fallback.png", "alt": "", "loading": "lazy"},
				styles={
					"aspectRatio": "1 / 1",
					"backgroundColor": refs["card"],
					"borderRadius": "10px",
					"display": "block",
					"objectFit": "cover",
					"width": "58px",
				},
				dynamicValues=[dv("image", "src", "attribute"), dv("product_name", "alt", "attribute")],
			),
			block(
				"div",
				styles={"display": "flex", "flexDirection": "column", "flexGrow": "1", "gap": "4px"},
				children=[
					block(
						"h3",
						text="Product",
						styles={"fontSize": "14px", "fontWeight": "500", "height": "fit-content", "width": "fit-content"},
						dynamicValues=[dv("product_name", "innerHTML")],
					),
					block(
						"p",
						text="",
						styles=mono(size="11px", color=refs["muted"], spacing="0.04em", upper=False),
						dynamicValues=[dv("formatted_rate", "innerHTML")],
					),
				],
			),
			block(
				"div",
				name="Qty",
				styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "8px"},
				children=[
					block(
						"button",
						text="−",
						attrs={"type": "button", "data-shop": "qty-dec", "aria-label": "Decrease quantity"},
						styles=dict(qty_button),
						dynamicValues=[dv("item_code", "data-item-code", "attribute")],
					),
					block(
						"span",
						text="1",
						styles={**mono(size="12px", color=refs["ink"], spacing="0", upper=False), "minWidth": "18px", "textAlign": "center"},
						dynamicValues=[dv("qty", "innerHTML")],
					),
					block(
						"button",
						text="+",
						attrs={"type": "button", "data-shop": "qty-inc", "aria-label": "Increase quantity"},
						styles=dict(qty_button),
						dynamicValues=[dv("item_code", "data-item-code", "attribute")],
					),
				],
			),
			block(
				"p",
				text="",
				styles={
					**mono(size="13px", weight="500", color=refs["ink"], spacing="0.02em", upper=False),
					"minWidth": "84px",
					"textAlign": "right",
				},
				dynamicValues=[dv("formatted_amount", "innerHTML")],
			),
			block(
				"button",
				text="Remove",
				attrs={"type": "button", "data-shop": "remove"},
				styles={
					**mono(size="10px", color=refs["muted"], spacing="0.12em"),
					"backgroundColor": "transparent",
					"borderWidth": "0px",
					"textDecoration": "underline",
				},
				dynamicValues=[dv("item_code", "data-item-code", "attribute")],
			),
		],
	)
	cart_panel = panel(
		refs,
		[
			block(
				"p",
				text="Your cart is empty.",
				visibilityCondition={"key": "cart.is_empty", "comesFrom": "dataScript"},
				styles=mono(size="12px", color=refs["muted"], spacing="0.12em"),
			),
			repeater(
				"cart.items",
				line_item,
				{"display": "flex", "flexDirection": "column", "marginTop": "-18px", "width": "100%"},
				name="Line Items",
			),
			block(
				"div",
				name="Totals",
				visibilityCondition={"key": "cart.item_count", "comesFrom": "dataScript"},
				styles={"display": "flex", "flexDirection": "column", "gap": "10px", "width": "100%"},
				children=[
					money_row(refs, "Subtotal", bound_key="cart.formatted_subtotal"),
					discount_row(refs, "cart.formatted_discount", "cart.coupon.code"),
					money_row(refs, "Total", bound_key="cart.formatted_total", strong=True),
					pill(refs, "Checkout", href="/checkout", full=True),
				],
			),
		],
		name="Section · Cart",
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack([page_header(refs, "( Cart )", "Your cart"), error_banner(refs), cart_panel]),
			component_ref("dot-footer"),
		],
	)


def submit_button(refs, text):
	node = pill(refs, text, attrs={"type": "submit"}, full=True)
	node["baseStyles"].update({"gridColumn": "span 2", "marginTop": "10px"})
	return node


def input_block(refs, name, label_text, input_type="text", required=False, half=False, prefill=False):
	attrs = {"type": input_type, "name": name, "placeholder": label_text}
	if required:
		attrs["required"] = "required"
	return block(
		"input",
		name=f"Input · {name}",
		attrs=attrs,
		dynamicValues=[dv(f"prefill.{name}", "value", "attribute")] if prefill else [],
		styles={**field_styles(refs), "gridColumn": "span 1" if half else "span 2"},
	)


def select_block(refs, name, data_key, label_text, required=False, half=False, prefill_key=None):
	"""Build a <select> whose <option>s are populated by a repeater from data_key."""
	option = block(
		"option",
		text="",
		dynamicValues=[dv("name", "innerHTML"), dv("name", "value", "attribute")],
	)
	attrs = {"name": name, "aria-label": label_text}
	if required:
		attrs["required"] = "required"
	sel = repeater(
		data_key,
		option,
		{**field_styles(refs), "gridColumn": "span 1" if half else "span 2"},
		element="select",
		attrs=attrs,
		name=f"Select · {name}",
	)
	# The repeater treats children[0] as the per-item template, so a static
	# placeholder option here would be repeated instead of the value option.
	# Required selects get their placeholder from initAddressDatalists instead.
	if prefill_key:
		sel["dynamicValues"] = [dv(prefill_key, "value", "attribute")]
	return sel


def coupon_box(refs):
	form = block(
		"form",
		name="Coupon Form",
		attrs={"data-shop": "coupon-form"},
		styles={"display": "flex", "flexDirection": "row", "gap": "8px", "width": "100%"},
		children=[
			block(
				"input",
				attrs={"type": "text", "name": "code", "placeholder": "Coupon code"},
				styles={**field_styles(refs, radius="999px"), "flexGrow": "1", "minWidth": "0px"},
			),
			pill(refs, "Apply", variant="outline", attrs={"type": "submit"}),
		],
	)
	applied = block(
		"div",
		name="Coupon Applied",
		visibilityCondition={"key": "cart.coupon.code", "comesFrom": "dataScript"},
		styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "10px", "width": "100%"},
		children=[
			block(
				"p",
				text="",
				styles={
					**mono(size="10px", weight="500", color=refs["ink"], spacing="0.12em"),
					"backgroundColor": refs["card"],
					"borderRadius": "999px",
					"padding": "5px 12px",
				},
				dynamicValues=[dv("cart.coupon.code", "innerHTML")],
			),
			block(
				"div",
				styles={"display": "flex", "flexDirection": "row", "flexGrow": "1", "justifyContent": "flex-end"},
				children=[
					run(refs, [(False, "−"), (True, "cart.coupon.formatted_discount")], size="12px", color=refs["accent"], family=MONO)
				],
			),
			block(
				"button",
				text="Remove",
				attrs={"type": "button", "data-shop": "coupon-remove"},
				styles={
					**mono(size="10px", color=refs["muted"], spacing="0.12em"),
					"backgroundColor": "transparent",
					"borderWidth": "0px",
					"textDecoration": "underline",
				},
			),
		],
	)
	return block(
		"div",
		name="Coupon",
		styles={
			"borderTopColor": refs["line"],
			"borderTopStyle": "solid",
			"borderTopWidth": "1px",
			"display": "flex",
			"flexDirection": "column",
			"gap": "12px",
			"paddingTop": "16px",
			"width": "100%",
		},
		children=[form, applied],
	)


def checkout_blocks(refs):
	payment_option = block(
		"label",
		name="Payment Method",
		styles={
			"alignItems": "center",
			"borderColor": refs["line"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"display": "flex",
			"flexDirection": "row",
			"gap": "10px",
			"padding": "12px 18px",
			"width": "100%",
		},
		children=[
			block(
				"input",
				attrs={"type": "radio", "name": "payment_method"},
				styles={"accentColor": refs["ink"], "height": "14px", "width": "14px"},
				dynamicValues=[dv("method", "value", "attribute")],
			),
			block(
				"span",
				text="Payment",
				styles=mono(size="11px", color=refs["ink"], spacing="0.1em"),
				dynamicValues=[dv("label", "innerHTML")],
			),
		],
	)
	form = block(
		"form",
		name="Checkout Form",
		attrs={"data-shop": "checkout-form"},
		styles={"display": "grid", "gap": "10px", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))", "width": "100%"},
		children=[
			block("p", text="Contact", styles={**mono(size="10px", color=refs["muted"], spacing="0.16em"), "gridColumn": "span 2"}),
			input_block(refs, "email", "Email address", "email", required=True, prefill=True),
			block(
				"p",
				text="Shipping address",
				styles={
					**mono(size="10px", color=refs["muted"], spacing="0.16em"),
					"gridColumn": "span 2",
					"marginTop": "12px",
				},
			),
			block(
				"div",
				name="Saved Addresses",
				visibilityCondition={"key": "has_addresses", "comesFrom": "dataScript"},
				styles={"display": "flex", "gridColumn": "span 2", "width": "100%"},
				children=[
					repeater(
						"addresses",
						block(
							"option",
							text="Address",
							dynamicValues=[dv("name", "value", "attribute"), dv("line", "innerHTML")],
						),
						field_styles(refs),
						element="select",
						attrs={"data-shop": "address-picker", "aria-label": "Saved addresses"},
					)
				],
			),
			input_block(refs, "full_name", "Full name", required=True, prefill=True),
			input_block(refs, "phone", "Phone", "tel", prefill=True),
			input_block(refs, "address_line1", "Address", required=True, prefill=True),
			input_block(refs, "address_line2", "Apartment, suite, etc. (optional)", prefill=True),
			input_block(refs, "landmark", "Nearest landmark", prefill=True),
			select_block(refs, "city", "address_cities", "City", required=True, half=True, prefill_key="prefill.city"),
			select_block(refs, "state", "address_provinces", "State / Province", half=True, prefill_key="prefill.state"),
			input_block(refs, "pincode", "Pincode", half=True, prefill=True),
			select_block(refs, "country", "address_country", "Country", half=True, prefill_key="prefill.country"),
			block(
				"p",
				text="Payment",
				styles={
					**mono(size="10px", color=refs["muted"], spacing="0.16em"),
					"gridColumn": "span 2",
					"marginTop": "12px",
				},
			),
			repeater(
				"payment_methods",
				payment_option,
				{"display": "flex", "flexDirection": "column", "gap": "8px", "gridColumn": "span 2", "width": "100%"},
				name="Payment Methods",
			),
			block(
				"p",
				text="You will be redirected to a secure payment gateway to complete your purchase.",
				attrs={"data-shop": "gateway-note", "hidden": "hidden"},
				styles={
					"color": refs["muted"],
					"fontSize": "12px",
					"gridColumn": "span 2",
					"height": "fit-content",
					"lineHeight": "1.5",
					"width": "100%",
				},
			),
			block(
				"div",
				name="Advance Instructions",
				attrs={"data-shop": "advance-instructions", "hidden": "hidden"},
				visibilityCondition={"key": "advance_instructions", "comesFrom": "dataScript"},
				styles={
					"borderColor": refs["line"],
					"borderRadius": "2px",
					"borderStyle": "solid",
					"borderWidth": "1px",
					"gridColumn": "span 2",
					"padding": "12px 14px",
					"width": "100%",
				},
				children=[
					block(
						"p",
						text="",
						styles={
							"color": refs["ink"],
							"fontSize": "12px",
							"fontWeight": "700",
							"lineHeight": "1.6",
							"whiteSpace": "pre-line",
							"width": "100%",
						},
						dynamicValues=[dv("advance_instructions", "innerHTML")],
					),
				],
			),
			# Raast has no gateway and no bank details to paste in before the
			# order exists — the QR is built from the order itself — so what it
			# says at this step is that. Shown exactly where Advance shows its
			# own note, keyed to the payment method the customer picked.
			block(
				"div",
				name="Raast Instructions",
				attrs={"data-shop": "raast-instructions", "hidden": "hidden"},
				visibilityCondition={"key": "raast_instructions", "comesFrom": "dataScript"},
				styles={
					"borderColor": refs["line"],
					"borderRadius": "2px",
					"borderStyle": "solid",
					"borderWidth": "1px",
					"gridColumn": "span 2",
					"padding": "12px 14px",
					"width": "100%",
				},
				children=[
					block(
						"p",
						text="",
						styles={
							"color": refs["ink"],
							"fontSize": "12px",
							"fontWeight": "700",
							"lineHeight": "1.6",
							"whiteSpace": "pre-line",
							"width": "100%",
						},
						dynamicValues=[dv("raast_instructions", "innerHTML")],
					),
				],
			),
			block(
				"div",
				name="Pickup Locations",
				attrs={"data-shop": "pickup-panel"},
				visibilityCondition={"key": "pickup_locations", "comesFrom": "dataScript"},
				dynamicValues=[dv("default_pickup_location", "data-default", "attribute")],
				styles={
					"display": "none",
					"flexDirection": "column",
					"gap": "10px",
					"gridColumn": "span 2",
					"width": "100%",
				},
				children=[
					block("p", text="Pickup location", styles=mono(size="10px", color=refs["muted"], spacing="0.16em")),
					repeater(
						"pickup_locations",
						block(
							"label",
							styles={
								"borderColor": refs["line"],
								"borderRadius": "2px",
								"borderStyle": "solid",
								"borderWidth": "1px",
								"cursor": "pointer",
								"display": "flex",
								"gap": "12px",
								"padding": "12px 14px",
								"width": "100%",
							},
							children=[
								block(
									"input",
									attrs={"type": "radio", "name": "pickup_location"},
									styles={"accentColor": refs["ink"], "height": "14px", "marginTop": "3px", "width": "14px"},
									dynamicValues=[dv("name", "value", "attribute")],
								),
								block(
									"div",
									styles={"display": "flex", "flexDirection": "column", "gap": "6px", "width": "100%"},
									children=[
										block(
											"p",
											text="",
											styles=mono(size="12px", color=refs["ink"], spacing="0.06em", weight="600"),
											dynamicValues=[dv("name", "innerHTML")],
										),
										block(
											"p",
											text="",
											styles={
												"color": refs["muted"],
												"fontSize": "12px",
												"height": "fit-content",
												"lineHeight": "1.5",
												"whiteSpace": "pre-line",
												"width": "100%",
											},
											dynamicValues=[dv("address", "innerHTML")],
											visibilityCondition={"key": "address", "comesFrom": "dataScript"},
										),
										map_frame(refs, "map_url"),
										directions_button(refs, "directions_url"),
										contact_buttons(refs, "phone_dial", "whatsapp_url", "phone"),
									],
								),
							],
						),
						{"display": "flex", "flexDirection": "column", "gap": "10px", "width": "100%"},
						name="Pickup Location Rows",
					),
					block(
						"p",
						text="Pay when you collect your order — no shipping fee.",
						styles={"color": refs["muted"], "fontSize": "12px", "lineHeight": "1.5", "width": "100%"},
					),
				],
			),
			submit_button(refs, "Place order"),
		],
	)
	summary_row = block(
		"div",
		name="Summary Row",
		styles={"alignItems": "center", "display": "flex", "flexDirection": "row", "gap": "12px", "width": "100%"},
		children=[
			block(
				"img",
				attrs={"src": "/assets/builder/images/fallback.png", "alt": "", "loading": "lazy"},
				styles={
					"aspectRatio": "1 / 1",
					"backgroundColor": refs["card"],
					"borderRadius": "8px",
					"display": "block",
					"objectFit": "cover",
					"width": "42px",
				},
				dynamicValues=[dv("image", "src", "attribute"), dv("product_name", "alt", "attribute")],
			),
			block(
				"div",
				styles={"display": "flex", "flexDirection": "column", "flexGrow": "1", "gap": "3px"},
				children=[
					block(
						"p",
						text="Item",
						styles={"fontSize": "13px", "fontWeight": "500", "height": "fit-content", "width": "fit-content"},
						dynamicValues=[dv("product_name", "innerHTML")],
					),
					block(
						"p",
						text="",
						styles=mono(size="10px", color=refs["muted"], spacing="0.08em"),
						dynamicValues=[dv("qty", "innerHTML")],
					),
				],
			),
			block(
				"p",
				text="",
				styles=mono(size="12px", weight="500", color=refs["ink"], spacing="0.02em", upper=False),
				dynamicValues=[dv("formatted_amount", "innerHTML")],
			),
		],
	)
	summary = panel(
		refs,
		[
			label(refs, "Order summary", element="h2"),
			repeater(
				"cart.items",
				summary_row,
				{"display": "flex", "flexDirection": "column", "gap": "14px", "width": "100%"},
				name="Summary Items",
			),
			coupon_box(refs),
			block(
				"div",
				attrs={"data-shop": "delivery-totals"},
				styles={
					"borderTopColor": refs["line"],
					"borderTopStyle": "solid",
					"borderTopWidth": "1px",
					"display": "flex",
					"flexDirection": "column",
					"gap": "10px",
					"paddingTop": "16px",
					"width": "100%",
				},
				children=[
					money_row(refs, "Subtotal", bound_key="cart.formatted_subtotal"),
					discount_row(refs, "cart.formatted_discount", "cart.coupon.code"),
					money_row(refs, "Shipping", bound_key="cart.formatted_shipping", static_value="Free"),
					money_row(refs, "Total", bound_key="cart.formatted_total", strong=True),
				],
			),
			block(
				"div",
				attrs={"data-shop": "pickup-totals"},
				visibilityCondition={"key": "pickup_view", "comesFrom": "dataScript"},
				styles={
					"borderTopColor": refs["line"],
					"borderTopStyle": "solid",
					"borderTopWidth": "1px",
					"display": "none",
					"flexDirection": "column",
					"gap": "10px",
					"paddingTop": "16px",
					"width": "100%",
				},
				children=[
					money_row(refs, "Subtotal", bound_key="cart.formatted_subtotal"),
					discount_row(refs, "cart.formatted_discount", "cart.coupon.code"),
					money_row(refs, "Shipping", bound_key="pickup_view.formatted_shipping", static_value="Free"),
					money_row(refs, "Total", bound_key="pickup_view.formatted_total", strong=True),
				],
			),
			block(
				"p",
				text="Secure checkout · 14 day easy returns",
				styles={**mono(size="9px", color=refs["muted"], spacing="0.14em"), "textAlign": "center", "width": "100%"},
			),
		],
		styles={"gap": "18px", "height": "fit-content"},
		name="Summary",
	)
	empty = panel(
		refs,
		[
			block("p", text="Your cart is empty.", styles=mono(size="12px", color=refs["ink"], spacing="0.12em")),
			pill(refs, "Continue shopping", href="/products", variant="outline"),
		],
		styles={"alignItems": "center", "gap": "16px", "padding": "60px 40px"},
		name="Empty Checkout",
	)
	empty["visibilityCondition"] = {"key": "cart.is_empty", "comesFrom": "dataScript"}
	grid = block(
		"div",
		visibilityCondition={"key": "cart.item_count", "comesFrom": "dataScript"},
		styles={
			"display": "grid",
			"gap": "16px",
			"gridTemplateColumns": "minmax(0, 3fr) minmax(0, 2fr)",
			"width": "100%",
		},
		mobile={"gap": "12px", "gridTemplateColumns": "minmax(0, 1fr)"},
		children=[panel(refs, [form], name="Section · Checkout Form"), summary],
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack([page_header(refs, "( Checkout )", "Checkout"), error_banner(refs), empty, grid]),
			component_ref("dot-footer"),
		],
	)


def confirmation_blocks(refs):
	item_row = block(
		"div",
		name="Order Item",
		styles={
			"alignItems": "center",
			"borderBottomColor": refs["line"],
			"borderBottomStyle": "solid",
			"borderBottomWidth": "1px",
			"display": "flex",
			"flexDirection": "row",
			"justifyContent": "space-between",
			"padding": "12px 0",
			"width": "100%",
		},
		children=[
			block(
				"div",
				styles={"alignItems": "baseline", "display": "flex", "flexDirection": "row", "gap": "10px"},
				children=[
					block(
						"p",
						text="Item",
						styles={"fontSize": "13px", "fontWeight": "500", "height": "fit-content", "width": "fit-content"},
						dynamicValues=[dv("item_name", "innerHTML")],
					),
					block(
						"p",
						text="",
						styles=mono(size="10px", color=refs["muted"], spacing="0.08em"),
						dynamicValues=[dv("qty", "innerHTML")],
					),
				],
			),
			block(
				"p",
				text="",
				styles=mono(size="12px", weight="500", color=refs["ink"], spacing="0.02em", upper=False),
				dynamicValues=[dv("formatted_amount", "innerHTML")],
			),
		],
	)
	progress_stage = block(
		"div",
		name="Progress Stage",
		classes=["progress-stage"],
		attrs={"data-shop": "progress-stage"},
		dynamicValues=[dv("done", "data-done", "attribute")],
		children=[
			block("span", classes=["stage-dot"]),
			block("p", text="Stage", classes=["stage-label"], dynamicValues=[dv("label", "innerHTML")]),
		],
	)
	progress = repeater(
		"order.progress",
		progress_stage,
		{"display": "flex", "flexDirection": "row", "width": "100%"},
		name="Order Progress",
		attrs={"data-shop": "order-progress"},
	)
	tile_body = lambda text, **extra: block(
		"p",
		text=text,
		styles={"color": refs["muted"], "fontSize": "12px", "height": "fit-content", "lineHeight": "1.55", "width": "100%"},
		**extra,
	)
	info_tile = lambda title, body, **extra: inset(
		refs,
		[block("p", text=title, styles=mono(size="10px", color=refs["ink"], spacing="0.14em")), tile_body(body)],
		**extra,
	)
	delivery_tile = inset(
		refs,
		[
			block("p", text="Delivery", styles=mono(size="10px", color=refs["ink"], spacing="0.14em")),
			tile_body(
				"Your order is with the courier.",
				dynamicValues=[dv("order.shipment.line", "innerHTML")],
				visibilityCondition={"key": "order.shipment.line", "comesFrom": "dataScript"},
			),
			block(
				"a",
				text="Track shipment",
				attrs={"target": "_blank", "rel": "noopener"},
				styles={**mono(size="10px", color=refs["ink"], spacing="0.12em"), "textDecoration": "underline"},
				dynamicValues=[dv("order.shipment.tracking_url", "href", "attribute")],
				visibilityCondition={"key": "order.shipment.tracking_url", "comesFrom": "dataScript"},
			),
		],
		name="Delivery Tile",
		visibilityCondition={"key": "order.shipment", "comesFrom": "dataScript"},
	)
	advance_tile = inset(
		refs,
		[
			block("p", text="Advance payment", styles=mono(size="10px", color=refs["ink"], spacing="0.14em")),
			tile_body(
				"",
				dynamicValues=[dv("order.advance_payment.line", "innerHTML")],
				visibilityCondition={"key": "order.advance_payment.line", "comesFrom": "dataScript"},
			),
			block(
				"p",
				text="",
				# The bank details are the tile's call to action: keep them in
				# the ink colour and bold so they cannot be missed.
				styles={"color": refs["ink"], "fontSize": "12px", "fontWeight": "700", "height": "fit-content", "lineHeight": "1.55", "width": "100%"},
				dynamicValues=[dv("order.advance_payment.instructions", "innerHTML")],
				visibilityCondition={"key": "order.advance_payment.instructions", "comesFrom": "dataScript"},
			),
		],
		name="Advance Tile",
		visibilityCondition={"key": "order.advance_payment", "comesFrom": "dataScript"},
	)
	pickup_tile = inset(
		refs,
		[
			block("p", text="Pickup", styles=mono(size="10px", color=refs["ink"], spacing="0.14em")),
			block(
				"p",
				text="",
				styles=mono(size="12px", color=refs["ink"], spacing="0.06em", weight="600"),
				dynamicValues=[dv("order.pickup_location.name", "innerHTML")],
				visibilityCondition={"key": "order.pickup_location.name", "comesFrom": "dataScript"},
			),
			tile_body(
				"",
				dynamicValues=[dv("order.pickup_location.address", "innerHTML")],
				visibilityCondition={"key": "order.pickup_location.address", "comesFrom": "dataScript"},
			),
			map_frame(refs, "order.pickup_location.map_url", height="150px", margin="4px"),
			directions_button(refs, "order.pickup_location.directions_url"),
			contact_buttons(refs, "order.pickup_location.phone_dial", "order.pickup_location.whatsapp_url", "order.pickup_location.phone"),
		],
		name="Pickup Tile",
		visibilityCondition={"key": "order.pickup_location", "comesFrom": "dataScript"},
	)
	# Raast pays the whole order in one scan, so it leaves the information
	# grid for a panel of its own directly under the total. It is not one
	# status among several — it is the single thing this page asks the
	# customer to do — so it is inverted against the paper panel: amount
	# first, the account under it, the code framed in white on the right.
	# Secondary text is the paper colour at a lower opacity rather than the
	# muted token, because muted is mixed for a light surface and falls out
	# of readable contrast once the panel flips to its dark-mode value,
	# while translucent paper holds on both sides of that flip.
	soft = lambda opacity: {"color": refs["paper"], "height": "fit-content", "opacity": str(opacity), "width": "100%"}
	payment_rule = lambda: block(
		"div", styles={"backgroundColor": refs["paper"], "height": "1px", "opacity": "0.16", "width": "100%"}
	)
	# On a dark panel the fill itself carries the weight, so the solid
	# treatment marks the one action that settles the payment and the
	# outline takes the secondary — the mirror of the paper panels above.
	payment_button = lambda text, solid, **extra: block(
		"button",
		text=text,
		styles={
			"backgroundColor": refs["paper"] if solid else "transparent",
			"borderColor": refs["paper"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"color": refs["ink"] if solid else refs["paper"],
			"flexBasis": "0",
			"flexGrow": "1",
			"fontFamily": MONO,
			"fontSize": "11px",
			"height": "fit-content",
			"letterSpacing": "0.14em",
			"minWidth": "150px",
			"padding": "13px 24px",
			"textAlign": "center",
			"textTransform": "uppercase",
		},
		**extra,
	)
	# Copy matters as much as the QR: the customer reading this on the very
	# phone they bank from cannot point that phone at its own screen, so the
	# IBAN and a paste-ready transfer note have to be one tap away.
	raast_copy = block(
		"div",
		styles={"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "10px", "marginTop": "auto", "width": "100%"},
		children=[
			payment_button(
				"Copy IBAN",
				solid=True,
				attrs={"type": "button", "data-shop": "raast-copy"},
				dynamicValues=[dv("order.raast.copy_iban", "data-copy", "attribute")],
				visibilityCondition={"key": "order.raast.copy_iban", "comesFrom": "dataScript"},
			),
			payment_button(
				"Copy details",
				solid=False,
				attrs={"type": "button", "data-shop": "raast-copy"},
				dynamicValues=[dv("order.raast.copy_details", "data-copy", "attribute")],
				visibilityCondition={"key": "order.raast.copy_details", "comesFrom": "dataScript"},
			),
		],
	)
	payment_detail = lambda label_text, value_styles, key: block(
		"div",
		styles={"display": "flex", "flexDirection": "column", "gap": "5px", "width": "100%"},
		# The label goes with the value: a heading left behind over an empty
		# row whenever the account is not configured reads as a bug.
		visibilityCondition={"key": key, "comesFrom": "dataScript"},
		children=[
			block(
				"p",
				text=label_text,
				styles={**mono(size="9px", color=refs["paper"], spacing="0.16em"), "opacity": "0.6"},
			),
			block("p", text="", styles=value_styles, dynamicValues=[dv(key, "innerHTML")]),
		],
	)
	# An anchor inherits reset.css's underline and link colour unless told
	# otherwise, exactly as the directions and contact pills are. href and
	# download are bound rather than static so the link can never save the
	# wrong image; the visibility key hides it until there is a QR at all.
	raast_download = block(
		"a",
		text="Download QR",
		attrs={"download": "", "data-shop": "raast-download", "href": "#"},
		styles={
			"backgroundColor": f"{refs['paper']} !important",
			"borderColor": refs["paper"],
			"borderRadius": "999px",
			"borderStyle": "solid",
			"borderWidth": "1px",
			"boxSizing": "border-box",
			"color": f"{refs['ink']} !important",
			"fontFamily": MONO,
			"fontSize": "11px",
			"height": "fit-content",
			"letterSpacing": "0.14em",
			"padding": "13px 24px",
			"textAlign": "center",
			"textDecoration": "none !important",
			"textTransform": "uppercase",
			"width": "100%",
		},
		dynamicValues=[
			dv("order.raast.qr_data_url", "href", "attribute"),
			dv("order.raast.download_name", "download", "attribute"),
		],
		visibilityCondition={"key": "order.raast.qr_data_url", "comesFrom": "dataScript"},
	)
	payment_section = block(
		"div",
		name="Payment Section",
		styles={
			"backgroundColor": refs["ink"],
			"borderRadius": "16px",
			"display": "flex",
			"flexDirection": "column",
			"gap": "18px",
			"padding": "26px",
			"width": "100%",
		},
		mobile={"padding": "20px 16px"},
		visibilityCondition={"key": "order.raast", "comesFrom": "dataScript"},
		children=[
			# What this panel is, and where the money stands. The chip is
			# bound to the ledger rather than hardcoded so it reads Paid on
			# its own once the transfer has been recorded.
			block(
				"div",
				styles={
					"alignItems": "center",
					"display": "flex",
					"flexDirection": "row",
					"flexWrap": "wrap",
					"gap": "10px",
					"justifyContent": "space-between",
					"width": "100%",
				},
				children=[
					block("p", text="Advance payment", styles=mono(size="10px", color=refs["paper"], spacing="0.18em")),
					block(
						"p",
						text="Unpaid",
						styles={
							**mono(size="9px", color=refs["paper"], spacing="0.14em"),
							"borderColor": refs["paper"],
							"borderRadius": "999px",
							"borderStyle": "solid",
							"borderWidth": "1px",
							"opacity": "0.75",
							"padding": "5px 12px",
						},
						dynamicValues=[dv("order.payment_status", "innerHTML")],
					),
				],
			),
			payment_rule(),
			block(
				"div",
				name="Payment Columns",
				styles={
					"alignItems": "stretch",
					"display": "grid",
					"gap": "28px",
					"gridTemplateColumns": "minmax(0, 1fr) minmax(0, 288px)",
					"width": "100%",
				},
				mobile={"gridTemplateColumns": "minmax(0, 1fr)"},
				children=[
					# Left: what is owed, and where to send it. The amount
					# leads because it is the figure the customer compares
					# against the total they have just agreed to.
					block(
						"div",
						styles={"display": "flex", "flexDirection": "column", "gap": "16px", "width": "100%"},
						children=[
							block(
								"p",
								text="",
								styles={
									"color": refs["paper"],
									"fontFamily": HEAD,
									"fontSize": "34px",
									"fontWeight": "500",
									"height": "fit-content",
									"letterSpacing": "-0.02em",
									"lineHeight": "1.1",
									"width": "100%",
								},
								mobile={"fontSize": "26px"},
								dynamicValues=[dv("order.raast.formatted_amount", "innerHTML")],
							),
							block(
								"p",
								text="",
								styles={**soft(0.72), "fontSize": "13px", "lineHeight": "1.6"},
								dynamicValues=[dv("order.raast.line", "innerHTML")],
								visibilityCondition={"key": "order.raast.line", "comesFrom": "dataScript"},
							),
							payment_rule(),
							payment_detail(
								"Account title",
								{
									"color": refs["paper"],
									"fontSize": "16px",
									"fontWeight": "600",
									"height": "fit-content",
									"letterSpacing": "-0.01em",
									"width": "100%",
								},
								"order.raast.account_title",
							),
							# The bank is read off the IBAN itself, so the panel
							# names the destination without the customer having
							# to work out which four characters mean which bank.
							payment_detail(
								"Bank",
								{
									"color": refs["paper"],
									"fontSize": "16px",
									"fontWeight": "600",
									"height": "fit-content",
									"letterSpacing": "-0.01em",
									"width": "100%",
								},
								"order.raast.bank",
							),
							payment_detail(
								"IBAN",
								{**mono(size="14px", weight="500", color=refs["paper"], spacing="0.06em", upper=False), "width": "100%"},
								"order.raast.iban",
							),
							raast_copy,
						],
					),
					# Right: the code in a slip of white so it can be scanned
					# straight off the screen, with the download under it for
					# the customer reading this on the same phone they would
					# have to bank from.
					block(
						"div",
						styles={
							"alignItems": "center",
							"display": "flex",
							"flexDirection": "column",
							"gap": "12px",
							"justifyContent": "flex-end",
							"width": "100%",
						},
						children=[
							block(
								"div",
								styles={
									"alignItems": "center",
									"backgroundColor": refs["paper"],
									"borderRadius": "12px",
									"display": "flex",
									"justifyContent": "center",
									"padding": "12px",
									"width": "100%",
								},
								children=[
									block(
										"img",
										attrs={"alt": "Raast QR code"},
										styles={
											"borderRadius": "6px",
											"display": "block",
											"flexShrink": "0",
											"height": "auto",
											"maxWidth": "100%",
											"width": "240px",
										},
										# The screen shows the bare code — the
										# captioned card is for the download,
										# where the picture outlives the page.
										dynamicValues=[dv("order.raast.qr_plain_url", "src", "attribute")],
										visibilityCondition={"key": "order.raast.qr_plain_url", "comesFrom": "dataScript"},
									),
								],
							),
							# The scan instruction sits with the code it describes, so
							# the copy above is free to carry the balance instead of
							# repeating the same "point your banking app at this" twice.
							block(
								"p",
								text="Raast QR code — scan with banking app",
								styles={**soft(0.6), "fontSize": "11px", "letterSpacing": "0.06em", "textAlign": "center"},
								visibilityCondition={"key": "order.raast.qr_plain_url", "comesFrom": "dataScript"},
							),
							raast_download,
						],
					),
				],
			),
			# The instructions take a rule of their own so they read as the
			# footnote they are, and go with it when none is configured.
			block(
				"div",
				styles={"display": "flex", "flexDirection": "column", "gap": "12px", "width": "100%"},
				visibilityCondition={"key": "order.raast.instructions", "comesFrom": "dataScript"},
				children=[
					payment_rule(),
					block(
						"p",
						text="",
						styles={**soft(0.72), "fontSize": "12px", "lineHeight": "1.6"},
						dynamicValues=[dv("order.raast.instructions", "innerHTML")],
					),
				],
			),
		],
	)
	order_panel = panel(
		refs,
		[
			progress,
			block(
				"div",
				styles={
					"alignItems": "baseline",
					"borderTopColor": refs["line"],
					"borderTopStyle": "solid",
					"borderTopWidth": "1px",
					"display": "flex",
					"flexDirection": "row",
					"justifyContent": "space-between",
					"paddingTop": "22px",
					"width": "100%",
				},
				children=[
					label(refs, "Order summary", element="h2"),
					block(
						"p",
						text="Order",
						styles=mono(size="10px", color=refs["muted"], spacing="0.1em"),
						dynamicValues=[dv("order.name", "innerHTML")],
					),
				],
			),
			repeater(
				"order.items",
				item_row,
				{"display": "flex", "flexDirection": "column", "marginTop": "-14px", "width": "100%"},
				name="Order Items",
			),
			block(
				"div",
				styles={"display": "flex", "flexDirection": "column", "gap": "10px", "width": "100%"},
				children=[
					money_row(refs, "Subtotal", bound_key="order.formatted_total"),
					discount_row(refs, "order.formatted_discount", "order.formatted_discount"),
					money_row(refs, "Shipping", bound_key="order.formatted_shipping", static_value="Free"),
					money_row(refs, "Total", bound_key="order.formatted_grand_total", strong=True),
				],
			),
			# Straight under the total: the figure the panel asks for is the
			# figure the customer just read, and nothing else competes for
			# the eye between the two.
			payment_section,
			block(
				"div",
				name="Order Tiles",
				classes=["order-tiles"],
				styles={"display": "grid", "gap": "12px", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))", "width": "100%"},
				mobile={"gridTemplateColumns": "minmax(0, 1fr)"},
				children=[
					delivery_tile,
					advance_tile,
					pickup_tile,
					# One grid for every tile, so the grid stays filled. The
					# notes used to sit in a row of their own, which forced a
					# break the moment any conditional tile rendered — a
					# pickup order put Receipt alone on a second row, under
					# the empty half beside Pickup. A block hidden by a
					# visibility condition is not rendered at all, so the
					# children here are exactly the tiles this order has, and
					# .order-tiles stretches the last of them across the row
					# whenever that count comes out odd.
					info_tile(
						"Shipping",
						"Your order ships in 48 hours. We will email you the tracking number.",
						name="Shipping Tile",
						visibilityCondition={"key": "order.awaiting_shipment", "comesFrom": "dataScript"},
					),
					info_tile("Receipt", "A confirmation for this order has been sent to your email address."),
				],
			),
			block(
				"div",
				styles={"display": "flex", "flexDirection": "row", "flexWrap": "wrap", "gap": "10px", "width": "100%"},
				children=[
					pill(refs, "Track my order", href="/account/orders"),
					pill(refs, "Continue shopping", href="/products", variant="outline"),
				],
			),
		],
		name="Section · Order",
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack(
				[
					page_header(
						refs,
						"( Confirmed )",
						"Thank you for your order!",
						"Your order is confirmed. A copy with tracking details is on its way to your email.",
					),
					order_panel,
					returns_panel(refs),
				]
			),
			component_ref("dot-footer"),
		],
	)


def returns_panel(refs):
	request_row = block(
		"div",
		name="Return Request",
		styles={
			"alignItems": "baseline",
			"borderBottomColor": refs["line"],
			"borderBottomStyle": "solid",
			"borderBottomWidth": "1px",
			"display": "flex",
			"flexDirection": "row",
			"gap": "12px",
			"justifyContent": "space-between",
			"padding": "12px 0",
			"width": "100%",
		},
		children=[
			block(
				"div",
				styles={"display": "flex", "flexDirection": "column", "gap": "4px"},
				children=[
					block(
						"p",
						text="Request",
						styles={"fontSize": "13px", "fontWeight": "500", "height": "fit-content", "width": "fit-content"},
						dynamicValues=[dv("line", "innerHTML")],
					),
					block(
						"p",
						text="",
						visibilityCondition={"key": "resolution_note", "comesFrom": "dataScript"},
						styles={"color": refs["muted"], "fontSize": "12px", "height": "fit-content", "lineHeight": "1.5", "width": "100%"},
						dynamicValues=[dv("resolution_note", "innerHTML")],
					),
				],
			),
			block(
				"p",
				text="Requested",
				styles=mono(size="10px", color=refs["muted"], spacing="0.12em"),
				dynamicValues=[dv("status", "innerHTML")],
			),
		],
	)
	item_option = block(
		"option",
		text="Item",
		dynamicValues=[dv("item_code", "value", "attribute"), dv("item_name", "innerHTML")],
	)
	form = block(
		"form",
		name="Return Form",
		attrs={"data-shop": "return-form"},
		visibilityCondition={"key": "order.returns.eligible", "comesFrom": "dataScript"},
		styles={"display": "flex", "flexDirection": "column", "gap": "10px", "width": "100%"},
		children=[
			block(
				"p",
				text="Something not right? You have 14 days from shipping to ask for a return or a replacement.",
				styles={"color": refs["muted"], "fontSize": "12px", "height": "fit-content", "lineHeight": "1.55", "width": "100%"},
			),
			block(
				"div",
				styles={"display": "grid", "gap": "10px", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))", "width": "100%"},
				mobile={"gridTemplateColumns": "minmax(0, 1fr)"},
				children=[
					repeater(
						"order.items",
						item_option,
						field_styles(refs),
						element="select",
						name="Item Select",
						attrs={"name": "item_code"},
					),
					block(
						"select",
						attrs={"name": "request_type"},
						styles=field_styles(refs),
						children=[
							block("option", text="Return", attrs={"value": "Return"}),
							block("option", text="Replacement", attrs={"value": "Replacement"}),
						],
					),
				],
			),
			block(
				"textarea",
				attrs={"name": "reason", "placeholder": "What went wrong?", "rows": "3", "required": "required"},
				styles=field_styles(refs),
			),
			pill(refs, "Submit request", variant="outline", attrs={"type": "submit"}),
		],
	)
	requests = repeater(
		"order.returns.requests",
		request_row,
		{"display": "flex", "flexDirection": "column", "width": "100%"},
		name="Return Requests",
		visibilityCondition={"key": "order.returns.has_requests", "comesFrom": "dataScript"},
	)
	node = panel(
		refs,
		[label(refs, "Returns & replacements", element="h2"), requests, form],
		styles={"gap": "18px"},
		name="Returns Panel",
	)
	node["visibilityCondition"] = {"key": "order.returns.show", "comesFrom": "dataScript"}
	return node


def account_blocks(refs):
	order_row = block(
		"a",
		name="Order Row",
		attrs={"data-shop": "order-link"},
		dynamicValues=[dv("url", "href", "attribute")],
		styles={
			"alignItems": "center",
			"borderBottomColor": refs["line"],
			"borderBottomStyle": "solid",
			"borderBottomWidth": "1px",
			"color": refs["ink"],
			"display": "grid",
			"gap": "16px",
			"gridTemplateColumns": "2fr 1fr 1fr 1fr",
			"padding": "16px 0",
			"textDecoration": "none",
			"width": "100%",
		},
		mobile={"gridTemplateColumns": "1fr 1fr"},
		children=[
			block(
				"p",
				text="Order",
				styles=mono(size="11px", weight="500", color=refs["ink"], spacing="0.06em", upper=False),
				dynamicValues=[dv("name", "innerHTML")],
			),
			block(
				"p",
				text="",
				styles=mono(size="10px", color=refs["muted"], spacing="0.08em"),
				dynamicValues=[dv("formatted_date", "innerHTML")],
			),
			block(
				"p",
				text="",
				styles=mono(size="10px", color=refs["success"], spacing="0.12em"),
				dynamicValues=[dv("display_status", "innerHTML")],
			),
			block(
				"p",
				text="",
				styles={
					**mono(size="12px", weight="500", color=refs["ink"], spacing="0.02em", upper=False),
					"justifySelf": "end",
				},
				dynamicValues=[dv("formatted_total", "innerHTML")],
			),
		],
	)
	orders_panel = panel(
		refs,
		[
			repeater(
				"orders",
				order_row,
				{"display": "flex", "flexDirection": "column", "marginTop": "-16px", "width": "100%"},
				name="Orders",
			)
		],
		name="Section · Orders",
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack([page_header(refs, "( Account )", "Your orders"), orders_panel]),
			component_ref("dot-footer"),
		],
	)


def about_blocks(refs):
	stat = lambda value, text: block(
		"div",
		styles={"display": "flex", "flexDirection": "column", "gap": "6px", "width": "100%"},
		children=[
			block("p", text=value, styles=mono(size="26px", weight="500", color=refs["ink"], spacing="-0.02em", upper=False)),
			block("p", text=text, styles=mono(size="10px", color=refs["muted"], spacing="0.14em")),
		],
	)
	content = panel(
		refs,
		[
			prose(
				refs,
				"This store exists to give you quality everyday essentials without the high price "
				"tag. We offer a mix of brand-new items alongside gently preloved—chosen because "
				"they are durable, practical, and made to last.",
				size="15px",
				width="min(620px, 100%)",
			),
			prose(
				refs,
				"Every pre-owned item is carefully inspected, cleaned, and described with complete "
				"honesty, so you always know what you’re getting. We keep our prices fair and "
				"stand behind every order. If something isn’t right when your box arrives, "
				"message us and we will fix it.",
				size="15px",
				width="min(620px, 100%)",
			),
			block(
				"div",
				styles={
					"borderTopColor": refs["line"],
					"borderTopStyle": "solid",
					"borderTopWidth": "1px",
					"display": "grid",
					"gap": "24px",
					# Two figures, not three. The orders-shipped claim is gone, so
					# this tracks the children rather than leaving a third empty
					# column behind.
					"gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
					"paddingTop": "28px",
					"width": "100%",
				},
				mobile={"gridTemplateColumns": "minmax(0, 1fr)"},
				children=[stat("2026", "Founded"), stat("48h", "Dispatch time")],
			),
		],
		name="Section · About",
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack([page_header(refs, "( About )", "Everything here earns its place."), content]),
			component_ref("dot-footer"),
		],
	)


def contact_blocks(refs):
	detail = lambda text, value: block(
		"div",
		styles={
			"borderBottomColor": refs["line"],
			"borderBottomStyle": "solid",
			"borderBottomWidth": "1px",
			"display": "flex",
			"flexDirection": "row",
			"justifyContent": "space-between",
			"padding": "16px 0",
			"width": "100%",
		},
		children=[
			block("p", text=text, styles=mono(size="10px", color=refs["muted"], spacing="0.14em")),
			block("p", text=value, styles=mono(size="11px", color=refs["ink"], spacing="0.04em", upper=False)),
		],
	)
	content = panel(
		refs,
		[
			prose(refs, "Questions about an order, a product or anything else. We reply within a day.", size="15px", width="min(520px, 100%)"),
			block(
				"div",
				styles={"display": "flex", "flexDirection": "column", "width": "100%"},
				children=[
					detail("Email", "relooppk@gmail.com"),
					detail("Phone", "+923106488879"),
					detail("Hours", "Mon to Fri, 10:00 to 18:00"),
				],
			),
			pill(refs, "Write to us", href="mailto:relooppk@gmail.com"),
		],
		name="Section · Contact",
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack([page_header(refs, "( Contact )", "Say hello."), content]),
			component_ref("dot-footer"),
		],
	)


FAQS = [
	("How long does delivery take?", "Orders are dispatched within 48 hours and usually arrive in 3 to 5 working days."),
	(
		"Can I return a product?",
		"Yes, within 14 days of delivery, unused and in its original packaging. Ask for a return from your order page and we will arrange a pickup.",
	),
	("How do sizes run?", "True to size with a modern fit. If you are between sizes, size up for a relaxed fit."),
	("How do I pay?", "You can pay online or choose cash on delivery at checkout."),
	("How do I track my order?", "Sign in with the email you used at checkout and open Account in the navigation."),
]


def faq_blocks(refs):
	entry = lambda question, answer: block(
		"div",
		styles={
			"borderBottomColor": refs["line"],
			"borderBottomStyle": "solid",
			"borderBottomWidth": "1px",
			"display": "flex",
			"flexDirection": "column",
			"gap": "8px",
			"padding": "20px 0",
			"width": "100%",
		},
		children=[
			block(
				"h3",
				text=question,
				styles={"fontSize": "15px", "fontWeight": "500", "height": "fit-content", "width": "100%"},
			),
			prose(refs, answer, size="13px"),
		],
	)
	content = panel(
		refs,
		[
			block(
				"div",
				styles={"display": "flex", "flexDirection": "column", "width": "100%"},
				children=[entry(question, answer) for question, answer in FAQS],
			),
			utility_row(refs, "Still stuck? Talk to support", "/contact"),
		],
		name="Section · FAQ",
	)
	return shell(
		refs,
		[
			component_ref("dot-navbar"),
			stack([page_header(refs, "( FAQ )", "Questions, answered."), content]),
			component_ref("dot-footer"),
		],
	)
