from toolkit import calculate as compute
import toolkit.reporting as reporting


def main():
    result = compute(3, 4)
    reporting.display(result)


if __name__ == "__main__":
    main()
