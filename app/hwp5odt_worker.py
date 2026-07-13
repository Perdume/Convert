"""HWP → ODT 변환 워커 (별도 프로세스로 실행).

pyhwp는 lxml이 있으면 생성한 ODT를 RelaxNG 스키마로 검증하고 실패 시 변환을
중단한다. 실제 문서의 스타일(조건부 스타일 맵 등)은 pyhwp 출력이 엄격한
스키마에 어긋나는 경우가 흔한데, LibreOffice는 그런 ODT도 문제없이 열므로
여기서는 검증을 끄고 변환한다.

별도 프로세스로 실행되므로 손상 파일로 인한 크래시가 서버로 전파되지 않는다.

사용법: python hwp5odt_worker.py <input.hwp> <output.odt>
"""
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: hwp5odt_worker.py <input.hwp> <output.odt>", file=sys.stderr)
        return 2

    src, dst = sys.argv[1], sys.argv[2]

    from hwp5.hwp5odt import ODTPackage, ODTTransform
    from hwp5.xmlmodel import Hwp5File

    class NoValidateODTTransform(ODTTransform):
        def make_odf_validator(self):
            return None

    transform = NoValidateODTTransform()
    pkg = ODTPackage(dst)
    try:
        hwp5file = Hwp5File(src)
        try:
            transform.transform_hwp5_to_package(hwp5file, pkg)
        finally:
            hwp5file.close()
    finally:
        pkg.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
