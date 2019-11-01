"""A set of common functions to be used by multiple parts of the code."""


class JandroidException(Exception):
    """Custom exception."""
    pass


class Conversions():
    """Conversion functions."""

    def __init__(self):
        pass

    def fn_smali_to_dotted(self, classpath):
        """Converts a path from smali representation to dotted (Java).

        :param classpath: path string to convert (from smali to Java)
        :returns: modified classpath
        :rtype: string
        """
        modified_classpath = classpath[1:]
        modified_classpath = modified_classpath.replace(';', '')
        modified_classpath = modified_classpath.replace('/', '.')
        return modified_classpath

    def fn_dotted_to_smali(self, classpath):
        """Converts a path from dotted (Java) representation to smali.
        
        :param classpath: path string to convert (from Java to smali)
        :returns: modified classpath
        :rtype: string
        """
        modified_classpath = classpath.replace('.', '/')
        modified_classpath = 'L' + modified_classpath + ';'
        return modified_classpath