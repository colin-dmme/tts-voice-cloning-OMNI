from typing import List, Optional

units = {
    '0': 'không',
    '1': 'một',
    '2': 'hai',
    '3': 'ba',
    '4': 'bốn',
    '5': 'năm',
    '6': 'sáu',
    '7': 'bảy',
    '8': 'tám',
    '9': 'chín',
}


def chunks(lst: List, n: int) -> List[List]:
    return [lst[i : i + n] for i in range(0, len(lst), n)]


def n2w_units(numbers: str) -> str:
    if not numbers:
        raise ValueError('Số rỗng!!')
    if len(numbers) > 1:
        raise ValueError('Số vượt quá giá trị của hàng đơn vị!')
    return units[numbers]


def pre_process_n2w(number: str) -> Optional[str]:
    clean = str(number).translate(str.maketrans('', '', ' -.,'))
    return clean if clean.isdigit() else None


def process_n2w_single(numbers: str) -> str:
    return ' '.join(units[d] for d in numbers if d in units)


def n2w_hundreds(numbers: str) -> str:
    if not numbers or numbers == '000':
        return ""

    n = numbers.zfill(3)
    h_digit, t_digit, u_digit = n[0], n[1], n[2]

    res = []

    if h_digit != '0':
        res.append(units[h_digit] + " trăm")
    elif len(numbers) == 3:
        res.append("không trăm")

    if t_digit == '0':
        if u_digit != '0' and (h_digit != '0' or len(numbers) == 3):
            res.append("lẻ")
    elif t_digit == '1':
        res.append("mười")
    else:
        res.append(units[t_digit] + " mươi")

    if u_digit != '0':
        if u_digit == '1' and t_digit not in ('0', '1'):
            res.append("mốt")
        elif u_digit == '5' and (t_digit != '0' or (h_digit != '0' or len(numbers) == 3)):
            res.append("lăm")
        else:
            res.append(units[u_digit])

    return " ".join(res)


def n2w_large_number(numbers: str) -> str:
    if not numbers or not numbers.lstrip('0'):
        return units['0']

    numbers = numbers.lstrip('0')

    n_len = len(numbers)
    groups = []
    for i in range(n_len, 0, -3):
        groups.append(numbers[max(0, i-3):i])

    suffixes = ['', ' nghìn', ' triệu', ' tỷ']

    parts = []
    for i, group in enumerate(groups):
        if group == '000':
            continue

        word = n2w_hundreds(group)
        if word:
            suffix_idx = i % 3
            main_suffix = suffixes[suffix_idx] if suffix_idx < len(suffixes) else ""

            tỷ_count = i // 3

            if main_suffix or tỷ_count > 0:
                full_suffix = main_suffix + (" tỷ" * tỷ_count)
                word_with_suffix = f"{word}{full_suffix}"
            else:
                word_with_suffix = word
            parts.append(word_with_suffix)

    if not parts:
        return units['0']

    parts.reverse()
    return ' '.join(parts).strip()


def n2w(number: str) -> str:
    clean_number = pre_process_n2w(number)
    if not clean_number:
        return str(number)

    if len(clean_number) == 2 and clean_number[0] == '0':
        return f"không {units[clean_number[1]]}"

    return n2w_large_number(clean_number)


def n2w_single(number: str) -> str:
    if str(number).startswith('+84'):
        number = '0' + str(number)[3:]
    clean_number = pre_process_n2w(number)
    if not clean_number:
        return str(number)
    return process_n2w_single(clean_number)
