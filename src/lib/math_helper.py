import math

def percentdiff(old, new):
    """ Calculate the precentage difference between old and new values
    
    .. note:: if old is 0 this function will reset it to 0.5
    
    :param old: old value
    :param new: new value
    :returns: percentage difference between old and new value
    
    """
    old = float(old)
    new = float(new)
    
    if old == 0 and new == 0:
            return 0
    elif old == 0:
        # % difference does not like original values of 0
        # setting to 0.5 makes growth from 0 to 1 = 100% change
        old = 0.5
 
    return (new - old)/old * 100

class SequentialSampleLinearRegression:
    """Class that calculates a simple linear regression from a list of values
    
    :param list y_values: list y values to run the linear regression on
    :param int sample_period: the sample period for the list of numbers
    
    .. note:: This class assumes that the list of values were sampled at a fixed period
    
    **Example**::
    
        data = [10, 20, 30, 40]
        sample_period = 5
        linear_regression = SimpleLinearRegression(data, sample_period)
        print linear_regression.slope
        print linear_regression.change

    **Author & License**:
    This is a modified version of the SimpleLinearRegression found at:
    http://code.activestate.com/recipes/578129-simple-linear-regression/
    The original class was licensed under the MIT license
    """
    _EPSILON = 0.0000001
    
    def __init__(self, y_values, sample_period):
        """ initializes members with defaults and runs regression 
        """
        self.sample_period  = sample_period
        self.y_values       = [float(i) for i in y_values]   
        self.x_values       = [float(i) for i in 
                               range(0, len(self.y_values)*sample_period, sample_period)]
        self.y_min          = min(self.y_values)
        self.y_max          = max(self.y_values)
        self.y_range        = self.y_max - self.y_min
        self.input_size     = len(self.y_values)
        self.intercept      = 0
        self.slope          = 0
        self.r              = 0
        self.change         = 0
        
        self._run_regression()
        
        return None
    
    def _run_regression(self):
        """ calculates coefficient of correlation and
            the parameters for the linear function 
        """
        n = float(len(self.y_values))
        
        sumX = sum(self.x_values)
        sumY = sum(self.y_values)
        sumXX = sum([x * x for x in self.x_values])
        sumYY = sum([y * y for y in self.y_values])
        sumXY = sum([x * y for x, y in zip(self.x_values, self.y_values)])
        
        denominator = math.sqrt((sumXX - 1 / n * sumX ** 2) * (sumYY - 1 / n * sumY ** 2))
        if denominator < self._EPSILON:
            return False
        
        # coefficient of correlation
        self.r = (sumXY - 1 / n * sumX * sumY)
        self.r /= denominator
        
        # is there no relationship between 'x' and 'y'?
        if abs(self.r) < self._EPSILON:
            return False
        
        # calculating 'a' and 'b' of y = a + b*x
        self.slope = sumXY - sumX * sumY / n
        self.slope /= (sumXX - sumX ** 2 / n)
        
        self.intercept = sumY - self.slope * sumX
        self.intercept /= n
        
        firstY = self._function(1)
        lastY  = self._function(self.input_size*self.sample_period)
                
        self.change = (lastY - firstY) / abs(firstY) * 100.0
        
        return None
    
    def _function(self, x):
        """ linear function (be aware of current
            coefficient of correlation 
        """
        return self.intercept + self.slope * x
    
    def __repr__(self):
        """ current linear function for print 
        """
        return "y = f(x) = %(intercept)f + %(slope)f*x" % self.__dict__
