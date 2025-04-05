/**
 * Deep clones a JavaScript object or array
 * @param {*} obj - The object to clone
 * @returns {*} A deep clone of the input
 */
export function deepClone(obj) {
    // Handle null and undefined
    if (obj === null || obj === undefined) {
        return obj;
    }

    // Handle primitive types
    if (typeof obj !== 'object') {
        return obj;
    }

    // Handle Date objects
    if (obj instanceof Date) {
        return new Date(obj.getTime());
    }

    // Handle Array objects
    if (Array.isArray(obj)) {
        return obj.map(item => deepClone(item));
    }

    // Handle regular objects
    const clonedObj = {};
    for (const key in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, key)) {
            clonedObj[key] = deepClone(obj[key]);
        }
    }
    return clonedObj;
}

/**
 * Creates a shallow clone of an object
 * @param {Object} obj - The object to clone
 * @returns {Object} A shallow clone of the input object
 */
export function shallowClone(obj) {
    if (Array.isArray(obj)) {
        return [...obj];
    }
    return Object.assign({}, obj);
}
