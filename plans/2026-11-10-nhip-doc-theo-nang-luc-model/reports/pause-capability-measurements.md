# Đo khoảng lặng thật sau dấu câu (pha 0)

Ngày 10/11/2026. Mỗi model đọc cùng một đoạn, tắt Ngắt nghỉ theo dấu câu và Nhịp đọc. Ô = trung vị ms (p10–p90), `đọc liền` = tỉ lệ dấu không có lặng ≥50ms.

Dòng `_nhip`: bật Nhịp đọc (toàn bộ, mặc định). Cột cuối: xếp N khoảng lặng dài nhất và N mục tiêu (quanh câu ngắn 700ms) theo độ dài, đếm cặp nằm trong [mục tiêu − 60, mục tiêu + 150] ms. Cách này không cần dóng từng dấu, nên không bị lệch khi giọng có nhiều chỗ ngắt.

| Model | phẩy , | ; : | … | . ! | ? | Đạt mục tiêu |
|---|---|---|---|---|---|---|
| piper_ngoc_huyen | 262 (244–312) | 174 (87–262) | 0, đọc liền 100% | 524 (424–624) | 544 (472–616) |  |
| piper_mai_phuong | 229 (218–246) | 224 (217–232) | 0, đọc liền 100% | 282 (267–296) | 366 (340–392) |  |
| piper_nguyet_nga | 244 (140–256) | 204 (173–236) | 215 (215–215) | 502 (477–533) | 584 (528–640) |  |
| supertonic_f1 | 389 (167–469) | 108 (66–150) | 140 (140–140) | 154 (71–287) | 262 (164–360) |  |
| kokoro_af_heart_en | 70 (55–248) | 325 (261–389) | 595 (595–595) | 290 (60–502) | 140 (80–200) |  |
| zerotts_official_huuduc | 195 (93–283), đọc liền 17% | 62 (52–72) | 280 (280–280) | 148 (64–294) | 212 (182–242) |  |
| vieneu_v3_pham_tuyen | 155 (54–308), đọc liền 17% | 88 (74–102) | 70 (70–70) | 465 (366–533) | 405 (301–509) |  |
| zerotts_q8_huuduc | 70 (62–158), đọc liền 17% | 55 (51–59) | 210 (210–210) | 272 (110–362) | 285 (269–301) |  |
| kokoro_param_s0_c0 | 70 (55–248) | 325 (261–389) | 595 (595–595) | 290 (60–502) | 140 (80–200) |  |
| kokoro_param_s250_c100 | 105 (105–255) | 325 (261–389) | 50 (50–50) | 505 (497–577), đọc liền 25% | 160 (84–236) |  |
| kokoro_param_s600_c300 | 305 (305–460) | 355 (315–395) | 50 (50–50) | 605 (605–605), đọc liền 25% | 335 (119–551) |  |
| kokoro_param_s1000_c500 | 505 (505–760) | 505 (505–505) | 50 (50–50) | 1005 (1005–1005), đọc liền 25% | 535 (159–911) |  |
| vieneu_v2_turbo_pham_tuyen | 340 (163–402), đọc liền 17% | 468 (454–482) | 315 (315–315) | 662 (558–679) | 632 (614–650) |  |
| omnivoice_hoang_quan | 150 (88–405) | 80 (56–104) | 150 (150–150) | 280 (216–467) | 395 (211–579) |  |
| chatterbox_johnny_en | 345 (152–558) | 380 (212–548) | 60 (60–60) | 550 (197–854) | 720 (688–752) |  |
| piper_ngoc_huyen_nhip | 234 (226–236) | 414 (414–414) | 0, đọc liền 100% | 668 (580–704) | 658 (635–682) | 10/15 |
| piper_nguyet_nga_nhip | 234 (222–237), đọc liền 17% | 412 (406–418) | 668 (668–668) | 690 (584–717) | 860 (726–994) | 14/15 |
| supertonic_f1_nhip | 326 (137–556) | 270 (150–389) | 718 (718–718) | 65 (56–237) | 636 (594–678) | 8/15 |
| kokoro_af_heart_en_nhip | 298 (172–488) | 348 (306–390) | 730 (730–730) | 432 (124–640) | 632 (586–678) | 10/15 |
| zerotts_official_huuduc_nhip | 175 (59–200), đọc liền 17% | 372 (354–390) | 690 (690–690) | 578 (184–694) | 658 (632–684) | 9/15 |
| vieneu_v3_pham_tuyen_nhip | 120 (50–272) | 390 (346–434) | 690 (690–690) | 668 (569–689) | 680 (676–684) | 14/15 |
| omnivoice_hoang_quan_nhip | 292 (130–395) | 255 (95–415) | 670 (670–670) | 520 (144–640), đọc liền 25% | 652 (622–682) | 8/15 |

## Chưa đo được

- `f5_hoang_quan`: RuntimeError: failed: ConfigError: F5-TTS v1 Base (SWivid) không hỗ trợ ngôn ngữ Tiếng Việt. Ngôn ngữ hỗ trợ: Tự động, English, Chinese.
- `qwen06_hoang_quan`: RuntimeError: failed: ConfigError: Qwen3 TTS 0.6B Base không hỗ trợ ngôn ngữ Tiếng Việt. Ngôn ngữ hỗ trợ: Tự động, English, Chinese, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian.
