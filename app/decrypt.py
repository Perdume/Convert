"""암호가 걸린 문서의 '암호 해제'.

중요: 이 모듈은 **사용자가 제공한 비밀번호**로만 암호를 해제한다. 비밀번호를
추측하거나 우회하지 않으며, 틀린 비밀번호에는 WrongPassword 를 던질 뿐이다.
(내 문서의 비밀번호를 입력해 암호를 푸는, Adobe·qpdf 등과 같은 일반적 기능)

지원:
  - PDF            : pikepdf (열기 비밀번호로 복호화 후 평문 PDF 저장)
  - MS 오피스 신형 : msoffcrypto-tool (암호화된 docx/xlsx/pptx)
  - MS 오피스 구형 : msoffcrypto-tool (RC4/CryptoAPI 방식 doc/xls/ppt 일부)
"""
from pathlib import Path


class WrongPassword(Exception):
    """비밀번호가 올바르지 않음."""


class DecryptError(Exception):
    """비밀번호는 맞아도 복호화/형식 해석에 실패함."""


def decrypt_pdf(src: Path, password: str, dst: Path) -> None:
    import pikepdf

    try:
        with pikepdf.open(str(src), password=password) as pdf:
            pdf.save(str(dst))
    except pikepdf.PasswordError:
        raise WrongPassword()
    except Exception as e:  # 손상 등
        raise DecryptError(str(e))


def decrypt_office(src: Path, password: str, dst: Path) -> None:
    """암호화된 오피스 파일을 평문 오피스 파일로 저장한다(형식은 유지).

    저장된 결과의 실제 하위 형식(docx/xls 등)은 호출부에서 다시 판별한다.
    """
    import msoffcrypto

    try:
        from msoffcrypto.exceptions import InvalidKeyError
    except Exception:  # 버전에 따라 경로가 없을 수 있음
        InvalidKeyError = ()  # type: ignore

    try:
        with open(src, "rb") as f:
            office = msoffcrypto.OfficeFile(f)
            office.load_key(password=password)
            with open(dst, "wb") as out:
                office.decrypt(out)
    except InvalidKeyError:
        raise WrongPassword()
    except Exception as e:
        # msoffcrypto 는 틀린 비밀번호에도 일반 예외를 던지는 경우가 있어
        # 메시지로 한 번 더 판별한다.
        msg = str(e).lower()
        if "password" in msg or "key" in msg or "incorrect" in msg or "verifier" in msg:
            raise WrongPassword()
        raise DecryptError(str(e))
