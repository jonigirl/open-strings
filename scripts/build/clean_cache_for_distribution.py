"""Explain why DataForge cache data must not be included in a distribution."""


def main():
    print("DataForge cache cleanup is not required for distribution.")
    print("Do not include user cache data: pristine/ and raw/ are created from Data.p4k at runtime.")


if __name__ == "__main__":
    main()
