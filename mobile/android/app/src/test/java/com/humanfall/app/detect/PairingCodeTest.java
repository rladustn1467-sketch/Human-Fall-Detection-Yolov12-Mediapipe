package com.humanfall.app.detect;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

/** The pairing-code field keeps only A-Z/0-9, upper-cased (typed or pasted). */
public class PairingCodeTest {
    @Test
    public void keepsLettersAndDigitsUpperCased() {
        assertEquals("A2B3C4", PairingCode.clean("A2B3C4"));
        assertEquals("A2B3C4", PairingCode.clean("a2b3c4"));                 // 소문자 → 대문자
    }

    @Test
    public void pastedTextIsCleaned() {
        assertEquals("A2B3C4", PairingCode.clean(" a2b 3c4\n"));             // 앞뒤·가운데 공백, 줄바꿈
        assertEquals("A2B3C4", PairingCode.clean("A2B-3C4"));
        assertEquals("KFXPTQ", PairingCode.clean("연결 코드: KFXPTQ"));       // 안내 문장째 붙여넣어도 코드만
    }

    @Test
    public void koreanKeyboardOutputIsDropped() {
        assertEquals("", PairingCode.clean("ㅏ릴트"));                        // 한글 자판으로 친 글자
        assertEquals("", PairingCode.clean(""));
        assertEquals("", PairingCode.clean(null));
        assertEquals("", PairingCode.clean("ＡＢＣ１２３"));                  // 전각 문자도 코드 아님
    }
}
