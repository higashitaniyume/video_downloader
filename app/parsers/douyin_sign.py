# -*- coding: utf-8 -*-
"""抖音 Web 端 a_bogus 签名生成（纯 Python，无第三方依赖）。

移植自 Johnserf-Seed/f2 (Apache License 2.0)
- https://github.com/Johnserf-Seed/f2
- 原始文件: f2/utils/abogus.py

改动说明:
- 移除 gmssl 依赖，内嵌纯 Python 的 SM3 实现（GB/T 32905-2016）。
- 对外只保留 generate_abogus() 入口。
"""

import random
import time
from typing import List, Optional, Union

# ---------------------------------------------------------------------------
# 纯 Python SM3 (GB/T 32905-2016)
# ---------------------------------------------------------------------------

_IV = [
    0x7380166F,
    0x4914B2B9,
    0x172442D7,
    0xDA8A0600,
    0xA96F30BC,
    0x163138AA,
    0xE38DEE4D,
    0xB0FB0E4E,
]

_TJ = [0x79CC4519, 0x7A879D8A]


def _rotl(x: int, n: int) -> int:
    n %= 32
    if n == 0:
        return x & 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _sm3_compress(state: List[int], block: bytes) -> List[int]:
    w = [0] * 68
    for i in range(16):
        w[i] = int.from_bytes(block[i * 4 : i * 4 + 4], "big")
    for i in range(16, 68):
        x = w[i - 16] ^ w[i - 9] ^ _rotl(w[i - 3], 15)
        w[i] = (
            x ^ _rotl(x, 15) ^ _rotl(x, 23) ^ _rotl(w[i - 13], 7) ^ w[i - 6]
        ) & 0xFFFFFFFF
    w1 = [0] * 64
    for i in range(64):
        w1[i] = (w[i] ^ w[i + 4]) & 0xFFFFFFFF

    a, b, c, d, e, f, g, h = state
    for j in range(64):
        t = 0 if j < 16 else 1
        ss1 = _rotl((_rotl(a, 12) + e + _rotl(_TJ[t], j)) & 0xFFFFFFFF, 7)
        ss2 = ss1 ^ _rotl(a, 12)
        if t == 0:
            tt1 = (a ^ b ^ c) + d + ss2 + w1[j]
            tt2 = (e ^ f ^ g) + h + ss1 + w[j]
        else:
            tt1 = ((a & b) | (a & c) | (b & c)) + d + ss2 + w1[j]
            tt2 = ((e & f) | ((~e) & g)) + h + ss1 + w[j]
        tt1 &= 0xFFFFFFFF
        tt2 &= 0xFFFFFFFF
        d, c, b, a = c, _rotl(b, 9), a, tt1
        h, g, f, e = (
            g,
            _rotl(f, 19),
            e,
            (tt2 ^ _rotl(tt2, 9) ^ _rotl(tt2, 17)) & 0xFFFFFFFF,
        )
    return [
        (state[0] ^ a) & 0xFFFFFFFF,
        (state[1] ^ b) & 0xFFFFFFFF,
        (state[2] ^ c) & 0xFFFFFFFF,
        (state[3] ^ d) & 0xFFFFFFFF,
        (state[4] ^ e) & 0xFFFFFFFF,
        (state[5] ^ f) & 0xFFFFFFFF,
        (state[6] ^ g) & 0xFFFFFFFF,
        (state[7] ^ h) & 0xFFFFFFFF,
    ]


def sm3_digest(data: bytes) -> bytes:
    """返回 data 的 32 字节 SM3 摘要。"""
    state = _IV[:]
    msg = bytearray(data)
    bit_len = len(msg) * 8
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += bit_len.to_bytes(8, "big")
    for i in range(0, len(msg), 64):
        state = _sm3_compress(state, bytes(msg[i : i + 64]))
    return b"".join(x.to_bytes(4, "big") for x in state)


# ---------------------------------------------------------------------------
# a_bogus 算法（移植自 f2，Apache-2.0）
# ---------------------------------------------------------------------------


class _StringProcessor:
    @staticmethod
    def to_char_array(s: str) -> List[int]:
        return [ord(c) for c in s]

    @staticmethod
    def to_char_str(byte_list: List[int]) -> str:
        return "".join(chr(b) for b in byte_list)

    @staticmethod
    def js_shift_right(val: int, n: int) -> int:
        return (val % 0x100000000) >> n

    @staticmethod
    def generate_random_bytes(length: int = 3) -> str:
        def generate_byte_sequence() -> List[str]:
            rd = int(random.random() * 10000)
            return [
                chr((rd & 255 & 170) | 1),
                chr((rd & 255 & 85) | 2),
                chr((_StringProcessor.js_shift_right(rd, 8) & 170) | 5),
                chr((_StringProcessor.js_shift_right(rd, 8) & 85) | 40),
            ]

        result = []
        for _ in range(length):
            result.extend(generate_byte_sequence())
        return "".join(result)


class _CryptoUtility:
    def __init__(self, salt: str, custom_base64_alphabet: List[str]):
        self.salt = salt
        self.base64_alphabet = custom_base64_alphabet
        self.big_array = [
            121, 243, 55, 234, 103, 36, 47, 228, 30, 231, 106, 6, 115, 95, 78,
            101, 250, 207, 198, 50, 139, 227, 220, 105, 97, 143, 34, 28, 194,
            215, 18, 100, 159, 160, 43, 8, 169, 217, 180, 120, 247, 45, 90,
            11, 27, 197, 46, 3, 84, 72, 5, 68, 62, 56, 221, 75, 144, 79, 73,
            161, 178, 81, 64, 187, 132, 63, 147, 146, 181, 80, 137, 24, 255,
            88, 245, 41, 122, 199, 133, 157, 252, 134, 240, 25, 23, 210, 173,
            223, 175, 189, 117, 190, 244, 31, 193, 140, 253, 163, 242, 170,
            108, 224, 158, 230, 201, 74, 116, 135, 91, 111, 19, 166, 152, 16,
            125, 225, 15, 229, 21, 149, 155, 188, 214, 96, 129, 87, 154, 107,
            13, 216, 182, 177, 61, 89, 109, 185, 123, 128, 236, 17, 211, 82,
            83, 209, 179, 110, 222, 142, 104, 69, 153, 114, 51, 151, 206, 141,
            4, 118, 119, 171, 238, 2, 60, 208, 14, 239, 127, 124, 213, 77,
            71, 162, 200, 113, 249, 219, 37, 150, 70, 148, 48, 66, 248, 20,
            218, 145, 174, 205, 10, 65, 130, 226, 184, 40, 86, 38, 167, 172,
            138, 93, 102, 203, 195, 99, 235, 104, 85, 241, 191, 202, 246, 136,
            176, 254, 192, 22, 29, 212, 168, 156, 204, 59, 126, 35, 94, 58,
            44, 12, 57, 92, 183, 98, 7, 67, 39, 251, 244, 112, 54, 233, 9,
            237, 232, 53, 22, 49, 52, 26, 42, 227, 131, 164, 196, 165, 205,
            202, 235, 137, 185,
        ]

    def complex_transform(
        self,
        input_data: str,
        first_num: int,
        second_num: int,
        third_array: List[int],
    ) -> str:
        s_arr = _StringProcessor.to_char_array(input_data)
        d_arr = list(range(256))
        c = 0
        transformed_result = []

        for i in range(256):
            c = (c + d_arr[i] + third_array[i % len(third_array)]) % 256
            d_arr[i], d_arr[c] = d_arr[c], d_arr[i]

        t = 0
        c = 0
        for b in s_arr:
            t = (t + first_num) % 256
            c = (c + d_arr[t]) % 256
            d_arr[t], d_arr[c] = d_arr[c], d_arr[t]
            transformed_result.append(b ^ d_arr[(d_arr[t] + d_arr[c]) % 256])

        return _StringProcessor.to_char_str(transformed_result)

    def custom_base64_encode(self, input_str: str) -> str:
        padding_char = "="
        byte_array = _StringProcessor.to_char_array(input_str)
        output = []
        i = 0

        while i < len(byte_array):
            b1 = byte_array[i]
            i += 1
            b2 = byte_array[i] if i < len(byte_array) else None
            i += 1
            b3 = byte_array[i] if i < len(byte_array) else None
            i += 1

            enc1 = b1 >> 2
            enc2 = ((b1 & 3) << 4) | ((b2 >> 4) if b2 is not None else 0)
            enc3 = (
                (((b2 & 15) << 2) | ((b3 >> 6) if b3 is not None else 0))
                if b2 is not None
                else None
            )
            enc4 = (b3 & 63) if b3 is not None else None

            if b2 is None:
                enc3 = enc4 = 64
            elif b3 is None:
                enc4 = 64

            output.append(self.base64_alphabet[enc1])
            output.append(self.base64_alphabet[enc2])
            output.append(
                self.base64_alphabet[enc3]
                if enc3 != 64
                else padding_char
            )
            output.append(
                self.base64_alphabet[enc4]
                if enc4 != 64
                else padding_char
            )

        return "".join(output)


class _AbogusAlgorithm:
    def __init__(self):
        self.crypto_util = _CryptoUtility(
            salt="y",
            custom_base64_alphabet=[
                "D", "k", "U", "m", "y", "l", "1", "z", "A", "E", "S", "t", "Z",
                "X", "o", "7", "P", "W", "v", "I", "n", "T", "u", "b", "r", "w",
                "8", "e", "V", "s", "K", "L", "5", "g", "0", "M", "N", "c", "d",
                "4", "O", "h", "x", "G", "i", "f", "R", "j", "C", "Y", "9", "2",
                "p", "a", "q", "3", "J", "H", "6", "Q", "B", "F", "-", "_",
            ],
        )

    def calculate_sm3_hash(self, input_data: Union[str, bytes]) -> List[int]:
        if isinstance(input_data, str):
            input_data = input_data.encode("utf-8")
        return list(sm3_digest(input_data))

    def generate_signature(
        self,
        request_params: str,
        request_body: str = "",
        user_agent: str = "",
        options: Optional[List[int]] = None,
        custom_timestamp: Optional[int] = None,
    ) -> str:
        if options is None:
            options = [0, 1, 14]

        # 三次连续 SM3 哈希处理参数与请求体
        params_hash = self.calculate_sm3_hash(
            self.calculate_sm3_hash(
                self.calculate_sm3_hash(request_params.encode("utf-8"))
            )
        )
        body_hash = self.calculate_sm3_hash(
            self.calculate_sm3_hash(
                self.calculate_sm3_hash(request_body.encode("utf-8"))
            )
        )
        ua_hash = self.calculate_sm3_hash(
            self.crypto_util.custom_base64_encode(
                self.crypto_util.complex_transform(
                    user_agent, 0x00000003, 0x00000055, self.crypto_util.big_array
                )
            ).encode("utf-8")
        )

        current_timestamp = (
            custom_timestamp if custom_timestamp is not None else int(time.time())
        )

        char_array = [
            180, options[0], options[1], options[2],
            params_hash[21], params_hash[22],
            body_hash[21], body_hash[22],
            ua_hash[21], ua_hash[22],
            _StringProcessor.js_shift_right(current_timestamp, 24) & 255,
            _StringProcessor.js_shift_right(current_timestamp, 16) & 255,
            _StringProcessor.js_shift_right(current_timestamp, 8) & 255,
            _StringProcessor.js_shift_right(current_timestamp, 0) & 255,
            _StringProcessor.js_shift_right(current_timestamp, 24) & 255,
            _StringProcessor.js_shift_right(current_timestamp, 16) & 255,
            _StringProcessor.js_shift_right(current_timestamp, 8) & 255,
            _StringProcessor.js_shift_right(current_timestamp, 0) & 255,
        ]

        checksum = char_array[0]
        for val in char_array[1:]:
            checksum ^= val
        char_array.append(checksum)

        data_string = _StringProcessor.to_char_str(char_array)
        random_bytes = _StringProcessor.generate_random_bytes(3)

        interleaved_bytes = (
            random_bytes[0] + data_string[0] +
            random_bytes[1] + data_string[1] +
            random_bytes[2] + data_string[2] +
            random_bytes[3] + data_string[3] +
            random_bytes[4] + data_string[4] +
            random_bytes[5] + data_string[5] +
            random_bytes[6] + data_string[6] +
            random_bytes[7] + data_string[7] +
            random_bytes[8] + data_string[8] +
            random_bytes[9] + data_string[9] +
            random_bytes[10] + data_string[10] +
            random_bytes[11] + data_string[11:]
        )

        transformed_data = self.crypto_util.complex_transform(
            interleaved_bytes,
            0x000000FF,
            0x00000018,
            _StringProcessor.to_char_array(self.crypto_util.salt),
        )

        return self.crypto_util.custom_base64_encode(transformed_data)


_signer = _AbogusAlgorithm()


def generate_abogus(
    params: str,
    body: str = "",
    user_agent: str = "",
    options: Optional[List[int]] = None,
    timestamp: Optional[int] = None,
) -> str:
    """生成 a_bogus 签名值。"""
    return _signer.generate_signature(
        params, body, user_agent, options, timestamp
    )
