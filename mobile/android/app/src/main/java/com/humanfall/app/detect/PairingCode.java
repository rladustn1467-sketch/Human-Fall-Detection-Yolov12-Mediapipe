package com.humanfall.app.detect;

/**
 * What the pairing-code field keeps from typed or pasted text: only A-Z and 0-9, upper-cased
 * (codes from the server are 6 letters/digits). Spaces, hyphens and anything a Korean keyboard
 * produces are dropped, so "a2b 3c4" or "A2B-3C4" become "A2B3C4". The server still checks the code.
 */
public final class PairingCode {
    private PairingCode() {
    }

    public static String clean(CharSequence text) {
        if (text == null) return "";
        StringBuilder out = new StringBuilder(text.length());
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c >= 'a' && c <= 'z') out.append((char) (c - 'a' + 'A'));
            else if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) out.append(c);
        }
        return out.toString();
    }
}
