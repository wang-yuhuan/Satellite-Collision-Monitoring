import pandas as pd
def save_to_csv(objCurrentRange, objCurrentRangeRate, filename="output.csv"):
    df = pd.DataFrame({
        'RelativeRange': objCurrentRange,
        'RelativeRangeRate': objCurrentRangeRate
    })
    df.to_csv(filename, index=False)
    print(f"结果已保存到 {filename}")